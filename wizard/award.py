import logging
from osv import osv, fields
from openerp.exceptions import ERPError
from fnx import date
ERPError

_logger = logging.getLogger(__name__)

class hr_training_award(osv.TransientModel):
    _name = 'hr.training.award'

    _columns = {
        'class_id': fields.many2one('hr.training.class', string='Class', oldname='class'),
        'employee_ids': fields.one2many('hr.training.award_status', 'master_id', string='Employees'),
        }

    def default_get(self, cr, uid, fields_list=None, context=None):
        ctx = context or {}
        source_id = ctx.get('active_id', False)
        fields_list = fields_list or []
        result = {}
        if 'class_id' in fields_list:
            result['class_id'] = source_id
        if 'employee_ids' in fields_list:
            employees = []
            hr_training_class = self.pool.get('hr.training.class')
            records = hr_training_class.browse(cr, uid, source_id, context=context).attendee_ids
            records.sort(key=lambda r: r.name)
            for rec in records:
                employees.append({
                    'employee_id': rec.id,
                    'name': rec.name,
                    'department': rec.department_id.name,
                    'job': rec.job_id.name,
                    'disposition': 'pass',
                    })
            result['employee_ids'] =  employees
        return result

    def cancel(self, cr, uid, ids, context=None):
        return True

    def process(self, cr, uid, ids, context=None):
        # add class to all employees' history
        # add tag to valid tags table
        # add certificate (tag) to all passing employees
        class_id = context.get('active_id')
        hr_training_class = self.pool.get('hr.training.class')
        hr_training_tag = self.pool.get('hr.training.tag')
        hr_training_history = self.pool.get('hr.training.history')
        hr_training_description = self.pool.get('hr.training.description')
        if not isinstance(ids, (int, long)):
            [ids] = ids
        this_rec = self.browse(cr, uid, ids, context=context)
        class_rec = hr_training_class.browse(cr, uid, class_id, context=context)
        cert_start_date = date(class_rec.start_date)
        if class_rec.duration_period == 'days':
            cert_start_date = cert_start_date.replace(delta_day=int(class_rec.duration_count)+1)
        cert_end_date = cert_start_date.replace(delta_month=class_rec.class_effective_period)
        passed_employees = [(6, 0, [e.employee_id.id for e in this_rec.employee_ids if e.disposition == 'pass'])]
        failed_employees = [(6, 0, [e.employee_id.id for e in this_rec.employee_ids if e.disposition == 'fail'])]
        instructor_ids = [(6, 0, [i.id for i in (class_rec.instructor_ids or [])])]
        history_rec = {
                'class_name': class_rec.class_name,
                'class_desc': class_rec.class_desc,
                'class_date': class_rec.start_date,
                'expiration_date': cert_end_date,
                }
        if passed_employees:
            # create certificate
            cert_rec = {
                'active': True,
                'name': '%s - %s' % (class_rec.class_cert, cert_end_date.strftime('%b %Y')),
                'start_date': cert_start_date,
                'end_date': cert_end_date,
                'employee_ids': passed_employees,
                'description_id': class_rec.description_id.id,
                }
            hr_training_tag.create(cr, uid, cert_rec, context=context)
            # add to history
            history_rec['disposition'] = 'pass'
            history_rec['class_cert'] = cert_rec['name']
            history_rec['employee_ids'] = passed_employees
            history_rec['instructor_ids'] = instructor_ids
            hr_training_history.create(cr, uid, history_rec, context=context)
            # add trained employees to class description
            tag_description = class_rec.description_id
            hr_training_description.write(
                    cr, uid, tag_description.id,
                    {'employee_ids': passed_employees},
                    context=context,
                    )
        if failed_employees:
            history_rec['disposition'] = 'fail'
            history_rec['class_cert'] = False
            history_rec['expiration_date'] = False
            history_rec['employee_ids'] = failed_employees
            history_rec['instructor_ids'] = instructor_ids
            hr_training_history.create(cr, uid, history_rec, context=context)
        hr_training_class.write(cr, uid, [class_id], {'active': False}, context=context)
        return True


class hr_training_award_status(osv.TransientModel):
    _name = 'hr.training.award_status'

    _columns = {
        'master_id': fields.many2one('hr.training.award'),
        'employee_id': fields.many2one('hr.employee', string='Employee'),
        'name': fields.char('Name', size=64),
        'department': fields.char('Department', size=64),
        'job': fields.char('Job', size=64),
        'disposition': fields.selection(
            (('pass', 'Pass'),
             ('fail', 'Fail'),
             ),
            string='Grant Certificate',
            sort_order='definition',
            ),
        }
