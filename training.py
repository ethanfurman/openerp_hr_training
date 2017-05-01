import logging
from osv import osv, fields
from fnx import construct_datetime
from openerp.exceptions import ERPError
# from dbf import Date

_logger = logging.getLogger(__name__)


class ClassLength(fields.SelectionEnum):
    _order_ = 'hours days'
    hours = 'Hours'
    days = 'Days'


class hr_training_description(osv.Model):
    _name = 'hr.training.description'
    _desc = 'class description'

    def _get_ids_from_tags(hr_training_tags, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        return [
                t.description_id.id
                for t in hr_training_tags.browse(cr, uid, ids, context=context)
                ]

    _columns = {
        'name': fields.char('Title', size=64),
        'desc': fields.text('Description'),
        'tag': fields.char('Certification Tag', size=64),
        'effective_period': fields.integer('Effective for'),
        'tag_ids': fields.one2many('hr.training.tag', 'description_id', 'Current Tags'),
        'class_ids': fields.one2many('hr.training.class', 'description_id', 'Classes'),
        'employee_ids': fields.many2many(
            'hr.employee',
            'employee2training_description', 'description_id', 'employee_id',
            string='Authorized Personnel',
            ),
        }


class hr_training_class(osv.Model):
    _name = 'hr.training.class'
    _desc = 'training class'
    _rec_name = 'class_name'

    def _calc_datetime(self, cr, uid, ids, field_name, arg, context=None):
        if isinstance(ids, (int, long)):
            ids = (ids, )
        res = {}
        for record in self.browse(cr, uid, ids, context=context):
            res[record.id] = construct_datetime(
                    record.start_date,
                    record.start_time,
                    context,
                    )
        return res

    def _remaining_seats(self, cr, uid, ids, field_name, arg, context=None):
        if isinstance(ids, (int, long)):
            ids = (ids, )
        res = {}
        for record in self.browse(cr, uid, ids, context=context):
            if record.capacity < 1:
                res[record.id] = -1
            else:
                res[record.id] = record.capacity - len(record.attendee_ids)
        return res

    _columns = {
        'active': fields.boolean('Pending', help='Class becomes inactive once completed'),
        'description_id': fields.many2one('hr.training.description', string='Class', ondelete='restrict'),
        'class_name': fields.related(
            'description_id', 'name',
            string='Name', type='char', size=64,
            ),
        'class_desc': fields.related(
            'description_id', 'desc',
            string='Description', type='text',
            ),
        'class_cert': fields.related(
            'description_id', 'tag',
            string='Certification', type='char', size=64,
            ),
        'class_effective_period': fields.related(
            'description_id', 'effective_period',
            string='Effective Period', type='integer',
            ),
        'duration_count': fields.integer('Length'),
        'duration_period': fields.selection(ClassLength, string='Class duration'),
        'start_date': fields.date('Start date'),
        'start_time': fields.char('Start time', size=12),
        'start_datetime': fields.function(
            _calc_datetime,
            string='Date & Time',
            type='datetime',
            store={
                'hr.training.class':
                    (lambda t, c, u, ids, ctx: ids, ['start_date', 'start_time'], 10),
                },
            ),
        'instructor_ids': fields.many2many(
            'res.partner',
            'instructor2training', 'training_id', 'partner_id',
            string='Instructor(s)',
            ),
        'attendee_ids': fields.many2many(
            'hr.employee',
            'employee2training_class', 'class_id', 'employee_id',
            string='Attendees', oldname='attendees',
            ),
        'location': fields.text('Class location'),
        'capacity': fields.integer('How many can attend'),
        'remaining': fields.function(
            _remaining_seats,
            string='Remaining seats',
            type='integer',
            store={
                'hr.training.class':
                    (lambda t, c, u, ids, ctx: ids, ['capacity', 'attendee_ids'], 10),
                },
            ),
        }

    _defaults = {
        'active': True,
        }

    def change_remaining(self, cr, uid, ids, capacity, attendee_ids, context=None):
        if capacity > 1:
            # count records
            taken = 0
            for action, id, values in attendee_ids:
                if action in (0, 1, 4):
                    taken += 1
                elif action in (2, 3):
                    taken -= 1
                elif action in (5, ):
                    taken = 0
                elif action in (6, ):
                    taken += len(values)
                else:
                    raise ERPError('Programming Error', 'many2many action %r is unknown' % action)

            remaining = capacity - taken
        else:
            remaining = -1
        return {'value': {'remaining': remaining}}

    def change_class(self, cr, uid, ids, desc_id, context=None):
        htd = self.pool.get('hr.training.description')
        res = {}
        record = htd.browse(cr, uid, desc_id, context=context)
        values = {
            'class_name': record.name,
            'class_desc': record.desc,
            'class_cert': record.tag,
            'class_effective_period': record.effective_period,
            }
        res['value'] = values
        return res


class hr_training_tag(osv.Model):
    _name = 'hr.training.tag'
    _desc = 'certification tag'

    _columns = {
        'active': fields.boolean('Effective', help="Tag becomes inactive once expired"),
        'description_id': fields.many2one('hr.training.description', 'Certificate Details'),
        'name': fields.char('Name', size=64),
        'employee_ids': fields.many2many(
            'hr.employee',
            'employee2training_tag', 'training_tag_id', 'employee_id',
            string='Certified Employees',
            ),
        'start_date': fields.date('Effective Date'),
        'end_date': fields.date('Expiration Date'),
        }


class hr_training_history(osv.Model):
    _name = 'hr.training.history'
    _desc = 'class taken by employee'

    _columns = {
        'employee_ids': fields.many2many(
            'hr.employee',
            'employee2training_history', 'history_id', 'employee_id',
            string='Employees',
            ),
        'instructor_ids': fields.many2many(
            'res.partner',
            'instructor2training_history', 'training_id', 'partner_id',
            string='Instructor(s)',
            on_delete='restrict',
            ),
        'disposition': fields.selection(
            (('pass', 'Passed'),
             ('fail', 'Failed'),
             ),
            string='Status',
            sort_order='definition',
            ),
        'class_name': fields.char('Class', size=64),
        'class_desc': fields.text('Description'),
        'class_cert': fields.char('Certificate', size=64),
        'class_date': fields.date('Training Date'),
        'expiration_date': fields.date('Expiration Date'),
        }


class hr_employee(osv.Model):
    _name = 'hr.employee'
    _inherit = 'hr.employee'

    _columns = {
        'hr_training_certs': fields.many2many(
            'hr.training.tag',
            'employee2training_tag', 'employee_id', 'training_tag_id',
            string='Certifications',
            ondelete='restrict',
            ),
        'hr_training_history': fields.many2many(
            'hr.training.history',
            'employee2training_history', 'employee_id', 'history_id',
            string='Training History',
            ),
        'hr_training_classes': fields.many2many(
            'hr.training.class',
            'employee2training_class', 'employee_id', 'class_id',
            string='Scheduled Training',
            ),
        }
