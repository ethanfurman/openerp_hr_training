import logging
from dbf import Date
from fnx import construct_datetime
from openerp import SUPERUSER_ID as SU
from openerp.exceptions import ERPError
from openerp.tools.misc import OrderBy, DEFAULT_SERVER_DATE_FORMAT
from osv import osv, fields

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
    _order = OrderBy("""coalesce(start_date, date '2001-01-01') desc""")

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
            string='Name', type='char', size=64, store=True,
            ),
        'class_desc': fields.related(
            'description_id', 'desc',
            string='Description', type='text', store=True,
            ),
        'class_cert': fields.related(
            'description_id', 'tag',
            string='Certification', type='char', size=64, store=True,
            ),
        'class_effective_period': fields.related(
            'description_id', 'effective_period',
            string='Effective Period', type='integer', store=True,
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
        'final_attendee_ids': fields.one2many(
            'hr.training.history', 'class_id',
            string='Final Attendees',
            ),
        'department': fields.many2one('hr.department', string='Department'),
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


class hr_training_trainee(osv.Model):
    _name = 'hr.training.trainee'

    _columns = {
        'employee_id': fields.many2one('hr.employee', 'Employee', ondelete='cascade'),
        'name': fields.related('employee_id', 'name', string='Name', type='char', size='64'),
        'certification_id': fields.many2one('hr.training.tag', 'Certification', ondelete='restrict'),
        'class_id': fields.many2one('hr.training.class', 'Training'),
        'disposition': fields.selection(
            (('pass', 'Passed'),
             ('fail', 'Failed'),
             ),
            string='Status',
            sort_order='definition',
            ),
        }


class hr_training_tag(osv.Model):
    _name = 'hr.training.tag'
    _desc = 'certification tag'

    def _calc_days(self, cr, uid, ids, field_name, arg, context):
        "number of days left before certification expires"
        res = {}
        if ids:
            today = Date.today()
            records = self.read(cr, uid, ids, ['id', 'end_date', 'active'], context)
            for rec in records:
                if not rec['active']:
                    continue
                id = rec['id']
                res[id] = {}
                expiration_date = Date.strptime(rec['end_date'], DEFAULT_SERVER_DATE_FORMAT)
                days_remaining = expiration_date - today
                res[id] = days_remaining.days
        return res

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
        'days_left': fields.function(
            _calc_days,
            method=True,
            type="integer",
            string='Effective days remaining',
            store={
                'hr.training.tag': (lambda table, cr, uid, ids, ctx: ids, ['active', 'end_date'], 10),
                },
            ),
        }

    def expire_tags(self, cr, uid, arg=None, context=None, ids=None):
        today = fields.date.today(self, cr, localtime=True)
        expired_ids = self.search(cr, uid, [('end_date','<',today)], context=context)
        self.write(cr, uid, expired_ids, {'active': False}, context=context)
        return True


class hr_training_history(osv.Model):
    _name = 'hr.training.history'
    _desc = 'class taken by employee'

    def _get_name(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        for rec in self.browse(cr, SU, ids, context=context):
            res[rec.id] = '%s: %s' % (rec.employee_name, rec.class_name)
        return res

    def _get_class_ids(key_table, cr, uid, ids, context=None):
        # ids are the ids changed in the foreign table
        # return the ids in this table that link to those foreign records
        self = key_table.pool.get('hr.training.history')
        return self.search(cr, SU, [('class_id','in',ids)], context=None)

    def _get_employee_ids(key_table, cr, uid, ids, context=None):
        # ids are the ids changed in the foreign table
        # return the ids in this table that link to those foreign records
        self = key_table.pool.get('hr.training.history')
        return self.search(cr, SU, [('employee_id','in',ids)], context=None)

    _columns = {
        'name': fields.function(
            _get_name,
            type='char',
            string='Name',
            store={
                'hr.employee': (_get_employee_ids, ['name'], 10),
                'hr.insurance.company': (_get_class_ids, ['class_name'], 10),
                }
            ),
        'employee_id': fields.many2one('hr.employee', 'Employee', ondelete='cascade'),
        'employee_name': fields.related('employee_id', 'name', string='Name', type='char', size=64),
        'employee_phone': fields.related('employee_id', 'work_phone', string='Phone', type='char', size=64),
        'employee_email': fields.related('employee_id', 'work_email', string='Email', type='char', size=128),
        'certification_id': fields.many2one('hr.training.tag', 'Certification', ondelete='restrict'),
        'class_cert': fields.related('certification_id', 'name', type='char', size=64),
        'expiration_date': fields.related(
            'certification_id', 'end_date',
            string='Expiration Date',
            type='date',
            ),
        'class_id': fields.many2one('hr.training.class', 'Training'),
        'class_name': fields.related('class_id', 'class_name', string='Class Name', type='char', size=64),
        'class_desc': fields.related('class_id', 'class_desc', string='Class Description', type='char', size=64),
        'class_date': fields.related('class_id', 'start_datetime', string='Class Date & Time', type='datetime'),
        'instructor_ids': fields.related(
            'class_id', 'instructor_ids',
            type='many2many',
            obj='res.partner',
            rel='instructor2training', id1='training_id', id2='partner_id',
            string='Instructors',
            ),
        'disposition': fields.selection(
            (('pass', 'Passed'),
             ('fail', 'Failed'),
             ('dna', 'D.N.A.'),
             ),
            string='Status',
            sort_order='definition',
            ),
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
        'hr_training_history': fields.one2many(
            'hr.training.history', 'employee_id',
            string='Training History',
            ),
        'hr_training_classes': fields.many2many(
            'hr.training.class',
            'employee2training_class', 'employee_id', 'class_id',
            string='Scheduled Training',
            ),
        }

    fields.apply_groups(
            _columns,
            {
                'base.group_hr_user': ['hr_training_.*'],
                })
