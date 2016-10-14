# -*- coding: utf-8 -*-

from openerp import models, fields, api

# class module_start(models.Model):
#     _name = 'module_start.module_start'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         self.value2 = float(self.value) / 100

class Course(models.Model):
    _name = 'redmine.course'
    _description = 'Redmine api'

    name = fields.Char(string="Title", required=True)
    description = fields.Text(string="Description", required=True)
    phone = fields.Integer(string="Phone", help='integer')
    email = fields.Char(string="Email", required=False)
    responsible_id = fields.Many2many('res.users',
        ondelete='set null', string="Responsible", index=True)
    attendee_ids = fields.Many2one('res.partner', string="Attendees")

class RedmineProject(models.Model):
    _name = 'redmine.project'
    _description = 'Redmine api'

    name = fields.Char(string="Title", required=True)
    description = fields.Text(string="Description", required=True)
    phone = fields.Integer(string="Phone", help='integer')
    email = fields.Char(string="Email", required=False)
    responsible_id = fields.Many2many('res.users',
        ondelete='set null', string="Responsible", index=True)
    attendee_ids = fields.Many2one('res.partner', string="Attendees")


### call object
Course()
