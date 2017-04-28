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
        if not source_id or 'employee_ids' not in (fields_list or []):
            return super(hr_training_award, self).default_get(cr, uid, fields_list=fields_list, context=context)
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
        result = {
            'class_id': source_id,
            'employee_ids': employees,
            }
        print 'returning', result
        return result

    def cancel(self, cr, uid, ids, context=None):
        return True

    def process(self, cr, uid, ids, context=None):
        # add class to all employees' history
        # add tag to valid tags table
        # add certificate (tag) to all passing employees
        print
        print ids
        print context
        print
        class_id = context.get('active_id')
        hr_training_class = self.pool.get('hr.training.class')
        hr_training_tag = self.pool.get('hr.training.tag')
        hr_training_history = self.pool.get('hr.training.history')
        if not isinstance(ids, (int, long)):
            [ids] = ids
        this_rec = self.browse(cr, uid, ids, context=context)
        print 'award', this_rec
        class_rec = hr_training_class.browse(cr, uid, class_id, context=context)
        print 'class', class_rec
        print 'start_date', class_rec.start_date
        cert_start_date = date(class_rec.start_date)
        print '--------->', cert_start_date
        if class_rec.duration_period == 'days':
            cert_start_date = cert_start_date.replace(delta_day=int(class_rec.duration_count)+1)
        print '--------->', cert_start_date
        cert_end_date = cert_start_date.replace(delta_month=class_rec.class_effective_period)
        print '>>>>>>>>>>', cert_end_date
        passed_employees = [6, 0, [e.id for e in this_rec.employee_ids if e.disposition == 'pass']]
        failed_employees = [6, 0, [e.id for e in this_rec.employee_ids if e.disposition == 'fail']]
        print 'all', this_rec.employee_ids
        print 'passed', passed_employees
        print 'failed', failed_employees
        instructor_ids = [(6, 0, [i.id for i in (class_rec.instructor_ids or [])])]
        history_rec = {
                'class_name': class_rec.class_name,
                'class_desc': class_rec.class_desc,
                'start_date': cert_start_date,
                'end_date': cert_end_date,
                }
        if passed_employees:
            cert_rec = {
                'active': True,
                'name': '%s - %s' % (class_rec.class_cert, cert_end_date.strftime('%b %Y')),
                'start_date': cert_start_date,
                'end_date': cert_end_date,
                }
            class_cert_id = hr_training_tag.create(cr, uid, cert_rec, context=context)
            hr_training_tag.write(
                    cr, uid, class_cert_id,
                    {'employee_ids': passed_employees},
                    context=context,
                    )
            history_rec['disposition'] = 'pass'
            history_rec['class_cert'] = class_cert_id
            history_id = hr_training_history.create(cr, uid, history_rec, context=context)
            hr_training_history.write(
                    cr, uid, history_id,
                    {'employee_ids': passed_employees, 'instructor_ids': instructor_ids},
                    context=context,
                    )
        if failed_employees:
            history_rec['disposition'] = 'fail'
            history_rec['class_cert'] = False
            history_id = hr_training_history.create(cr, uid, history_rec, context=context)
            hr_training_history.write(
                    cr, uid, history_id,
                    {'employee_ids': failed_employees, 'instructor_ids': instructor_ids},
                    context=context,
                    )
        # hr_training_class.write(cr, uid, [ids], {'active': False}, context=context)
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
