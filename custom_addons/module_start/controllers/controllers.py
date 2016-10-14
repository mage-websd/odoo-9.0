# -*- coding: utf-8 -*-
# from openerp import http
# from openerp.http import request
# from web.controllers import main, pivot

import logging
import json
import openerp
from openerp import http
from openerp.http import request
from redmine import Redmine
from .. import settings

_logger = logging.getLogger(__name__)

class ModuleStart(http.Controller):
    @http.route('/web/redmine/project', auth='user', website=True, methods=['POST'])
    def index(self, **kw):
        response = {}
        redmine = Redmine(settings.REDMINE_URL, key=settings.REDMINE_KEY)

        project = redmine.project.get('du-an-test')
        projects = redmine.project.all()
        
        redmineProject = []
        for item in projects:
            redmineProject.append({
                'id': item.id,
                'identifier': item.identifier,
                'name': item.name,
                'status': item.status,
                'created_on': item.created_on.strftime('%d/%m/%Y'),
                'issue_count': len(list(redmine.issue.filter(project_id=item.id, status_id='*'))),
                'issue_count_open': len(list(redmine.issue.filter(project_id=item.id, status_id='open'))),
                'issue_count_closed': len(list(redmine.issue.filter(project_id=item.id, status_id='closed'))),
            })

        response['success'] = 1
        response['data'] = redmineProject
        return json.dumps(response)
