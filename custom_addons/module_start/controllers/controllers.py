# -*- coding: utf-8 -*-
from openerp import http

# class ModuleStart(http.Controller):
#     @http.route('/module_start/module_start/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/module_start/module_start/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('module_start.listing', {
#             'root': '/module_start/module_start',
#             'objects': http.request.env['module_start.module_start'].search([]),
#         })

#     @http.route('/module_start/module_start/objects/<model("module_start.module_start"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('module_start.object', {
#             'object': obj
#         })
class ModuleStart(http.Controller):
    @http.route('/redmine/', auth='public', website=True)
    def index(self, **kw):
        # return http.request.render('newpage.index')
        return http.request.render('module_start.redmine_index')
        
    @http.route('/redmine/project/all/', auth='public')
    def list(self, **kw):
        return http.request.render('openacademy.listing', {
            'root': '/openacademy/openacademy',
            'objects': http.request.env['openacademy.openacademy'].search([]),
        })

    @http.route('/openacademy/openacademy/objects/<model("openacademy.openacademy"):obj>/', auth='public')
    def object(self, obj, **kw):
        return http.request.render('openacademy.object', {
            'object': obj
        })