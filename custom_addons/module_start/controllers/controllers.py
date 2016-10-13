# -*- coding: utf-8 -*-
# from openerp import http
# from openerp.http import request
# from web.controllers import main, pivot

import base64
import csv
import functools
import glob
import imghdr
import itertools
import jinja2
import logging
import operator
import datetime
import hashlib
import os
import re
import json
import sys
import time
import zlib
from xml.etree import ElementTree
from cStringIO import StringIO

import babel.messages.pofile
import werkzeug.utils
import werkzeug.wrappers
from openerp.api import Environment

import openerp
import openerp.modules.registry
from openerp.addons.base.ir.ir_qweb import AssetsBundle, QWebTemplateNotFound
from openerp.modules import get_resource_path
from openerp.tools import topological_sort
from openerp.tools.translate import _
from openerp.tools import ustr
from openerp.tools.misc import str2bool, xlwt
from openerp import http
from openerp.http import request, serialize_exception as _serialize_exception, content_disposition
from openerp.exceptions import AccessError

_logger = logging.getLogger(__name__)

if hasattr(sys, 'frozen'):
    # When running on compiled windows binary, we don't have access to package loader.
    path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'views'))
    loader = jinja2.FileSystemLoader(path)
else:
    loader = jinja2.PackageLoader('openerp.addons.web', "views")

env = jinja2.Environment(loader=loader, autoescape=True)
env.filters["json"] = json.dumps

# 1 week cache for asset bundles as advised by Google Page Speed
BUNDLE_MAXAGE = 60 * 60 * 24 * 7

#----------------------------------------------------------
# OpenERP Web helpers
#----------------------------------------------------------

db_list = http.db_list

db_monodb = http.db_monodb

def serialize_exception(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception, e:
            _logger.exception("An exception occured during an http request")
            se = _serialize_exception(e)
            error = {
                'code': 200,
                'message': "Odoo Server Error",
                'data': se
            }
            return werkzeug.exceptions.InternalServerError(json.dumps(error))
    return wrap

def redirect_with_hash(*args, **kw):
    """
        .. deprecated:: 8.0

        Use the ``http.redirect_with_hash()`` function instead.
    """
    return http.redirect_with_hash(*args, **kw)

def abort_and_redirect(url):
    r = request.httprequest
    response = werkzeug.utils.redirect(url, 302)
    response = r.app.get_response(r, response, explicit_session=False)
    werkzeug.exceptions.abort(response)

def ensure_db(redirect='/web/database/selector'):
    # This helper should be used in web client auth="none" routes
    # if those routes needs a db to work with.
    # If the heuristics does not find any database, then the users will be
    # redirected to db selector or any url specified by `redirect` argument.
    # If the db is taken out of a query parameter, it will be checked against
    # `http.db_filter()` in order to ensure it's legit and thus avoid db
    # forgering that could lead to xss attacks.
    db = request.params.get('db') and request.params.get('db').strip()

    # Ensure db is legit
    if db and db not in http.db_filter([db]):
        db = None

    if db and not request.session.db:
        # User asked a specific database on a new session.
        # That mean the nodb router has been used to find the route
        # Depending on installed module in the database, the rendering of the page
        # may depend on data injected by the database route dispatcher.
        # Thus, we redirect the user to the same page but with the session cookie set.
        # This will force using the database route dispatcher...
        r = request.httprequest
        url_redirect = r.base_url
        if r.query_string:
            # Can't use werkzeug.wrappers.BaseRequest.url with encoded hashes:
            # https://github.com/amigrave/werkzeug/commit/b4a62433f2f7678c234cdcac6247a869f90a7eb7
            url_redirect += '?' + r.query_string
        response = werkzeug.utils.redirect(url_redirect, 302)
        request.session.db = db
        abort_and_redirect(url_redirect)

    # if db not provided, use the session one
    if not db and request.session.db and http.db_filter([request.session.db]):
        db = request.session.db

    # if no database provided and no database in session, use monodb
    if not db:
        db = db_monodb(request.httprequest)

    # if no db can be found til here, send to the database selector
    # the database selector will redirect to database manager if needed
    if not db:
        werkzeug.exceptions.abort(werkzeug.utils.redirect(redirect, 303))

    # always switch the session to the computed db
    if db != request.session.db:
        request.session.logout()
        abort_and_redirect(request.httprequest.url)

    request.session.db = db

def module_installed(environment):
    # Candidates module the current heuristic is the /static dir
    loadable = http.addons_manifest.keys()

    # Retrieve database installed modules
    # TODO The following code should move to ir.module.module.list_installed_modules()
    Modules = environment['ir.module.module']
    domain = [('state','=','installed'), ('name','in', loadable)]
    modules = {
        module.name: module.dependencies_id.mapped('name')
        for module in Modules.search(domain)
    }

    sorted_modules = topological_sort(modules)
    return sorted_modules

def module_installed_bypass_session(dbname):
    try:
        registry = openerp.modules.registry.RegistryManager.get(dbname)
        with registry.cursor() as cr:
            return module_installed(
                environment=Environment(cr, openerp.SUPERUSER_ID, {}))
    except Exception:
        pass
    return {}

def module_boot(db=None):
    server_wide_modules = openerp.conf.server_wide_modules or ['web']
    serverside = []
    dbside = []
    for i in server_wide_modules:
        if i in http.addons_manifest:
            serverside.append(i)
    monodb = db or db_monodb()
    if monodb:
        dbside = module_installed_bypass_session(monodb)
        dbside = [i for i in dbside if i not in serverside]
    addons = serverside + dbside
    return addons

def concat_xml(file_list):
    """Concatenate xml files

    :param list(str) file_list: list of files to check
    :returns: (concatenation_result, checksum)
    :rtype: (str, str)
    """
    checksum = hashlib.new('sha1')
    if not file_list:
        return '', checksum.hexdigest()

    root = None
    for fname in file_list:
        with open(fname, 'rb') as fp:
            contents = fp.read()
            checksum.update(contents)
            fp.seek(0)
            xml = ElementTree.parse(fp).getroot()

        if root is None:
            root = ElementTree.Element(xml.tag)
        #elif root.tag != xml.tag:
        #    raise ValueError("Root tags missmatch: %r != %r" % (root.tag, xml.tag))

        for child in xml.getchildren():
            root.append(child)
    return ElementTree.tostring(root, 'utf-8'), checksum.hexdigest()

def fs2web(path):
    """convert FS path into web path"""
    return '/'.join(path.split(os.path.sep))

def manifest_glob(extension, addons=None, db=None, include_remotes=False):
    if addons is None:
        addons = module_boot(db=db)
    else:
        addons = addons.split(',')
    r = []
    for addon in addons:
        manifest = http.addons_manifest.get(addon, None)
        if not manifest:
            continue
        # ensure does not ends with /
        addons_path = os.path.join(manifest['addons_path'], '')[:-1]
        globlist = manifest.get(extension, [])
        for pattern in globlist:
            if pattern.startswith(('http://', 'https://', '//')):
                if include_remotes:
                    r.append((None, pattern))
            else:
                for path in glob.glob(os.path.normpath(os.path.join(addons_path, addon, pattern))):
                    r.append((path, fs2web(path[len(addons_path):])))
    return r

def manifest_list(extension, mods=None, db=None, debug=None):
    """ list ressources to load specifying either:
    mods: a comma separated string listing modules
    db: a database name (return all installed modules in that database)
    """
    if debug is not None:
        _logger.warning("openerp.addons.web.main.manifest_list(): debug parameter is deprecated")
    files = manifest_glob(extension, addons=mods, db=db, include_remotes=True)
    return [wp for _fp, wp in files]

def get_last_modified(files):
    """ Returns the modification time of the most recently modified
    file provided

    :param list(str) files: names of files to check
    :return: most recent modification time amongst the fileset
    :rtype: datetime.datetime
    """
    files = list(files)
    if files:
        return max(datetime.datetime.fromtimestamp(os.path.getmtime(f))
                   for f in files)
    return datetime.datetime(1970, 1, 1)

def make_conditional(response, last_modified=None, etag=None, max_age=0):
    """ Makes the provided response conditional based upon the request,
    and mandates revalidation from clients

    Uses Werkzeug's own :meth:`ETagResponseMixin.make_conditional`, after
    setting ``last_modified`` and ``etag`` correctly on the response object

    :param response: Werkzeug response
    :type response: werkzeug.wrappers.Response
    :param datetime.datetime last_modified: last modification date of the response content
    :param str etag: some sort of checksum of the content (deep etag)
    :return: the response object provided
    :rtype: werkzeug.wrappers.Response
    """
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = max_age
    if last_modified:
        response.last_modified = last_modified
    if etag:
        response.set_etag(etag)
    return response.make_conditional(request.httprequest)

def login_and_redirect(db, login, key, redirect_url='/web'):
    request.session.authenticate(db, login, key)
    return set_cookie_and_redirect(redirect_url)

def set_cookie_and_redirect(redirect_url):
    redirect = werkzeug.utils.redirect(redirect_url, 303)
    redirect.autocorrect_location_header = False
    return redirect

def load_actions_from_ir_values(key, key2, models, meta):
    Values = request.session.model('ir.values')
    actions = Values.get(key, key2, models, meta, request.context)

    return [(id, name, clean_action(action))
            for id, name, action in actions]

def clean_action(action):
    action.setdefault('flags', {})
    action_type = action.setdefault('type', 'ir.actions.act_window_close')
    if action_type == 'ir.actions.act_window':
        return fix_view_modes(action)
    return action

# I think generate_views,fix_view_modes should go into js ActionManager
def generate_views(action):
    """
    While the server generates a sequence called "views" computing dependencies
    between a bunch of stuff for views coming directly from the database
    (the ``ir.actions.act_window model``), it's also possible for e.g. buttons
    to return custom view dictionaries generated on the fly.

    In that case, there is no ``views`` key available on the action.

    Since the web client relies on ``action['views']``, generate it here from
    ``view_mode`` and ``view_id``.

    Currently handles two different cases:

    * no view_id, multiple view_mode
    * single view_id, single view_mode

    :param dict action: action descriptor dictionary to generate a views key for
    """
    view_id = action.get('view_id') or False
    if isinstance(view_id, (list, tuple)):
        view_id = view_id[0]

    # providing at least one view mode is a requirement, not an option
    view_modes = action['view_mode'].split(',')

    if len(view_modes) > 1:
        if view_id:
            raise ValueError('Non-db action dictionaries should provide '
                             'either multiple view modes or a single view '
                             'mode and an optional view id.\n\n Got view '
                             'modes %r and view id %r for action %r' % (
                view_modes, view_id, action))
        action['views'] = [(False, mode) for mode in view_modes]
        return
    action['views'] = [(view_id, view_modes[0])]

def fix_view_modes(action):
    """ For historical reasons, OpenERP has weird dealings in relation to
    view_mode and the view_type attribute (on window actions):

    * one of the view modes is ``tree``, which stands for both list views
      and tree views
    * the choice is made by checking ``view_type``, which is either
      ``form`` for a list view or ``tree`` for an actual tree view

    This methods simply folds the view_type into view_mode by adding a
    new view mode ``list`` which is the result of the ``tree`` view_mode
    in conjunction with the ``form`` view_type.

    TODO: this should go into the doc, some kind of "peculiarities" section

    :param dict action: an action descriptor
    :returns: nothing, the action is modified in place
    """
    if not action.get('views'):
        generate_views(action)

    if action.pop('view_type', 'form') != 'form':
        return action

    if 'view_mode' in action:
        action['view_mode'] = ','.join(
            mode if mode != 'tree' else 'list'
            for mode in action['view_mode'].split(','))
    action['views'] = [
        [id, mode if mode != 'tree' else 'list']
        for id, mode in action['views']
    ]

    return action

def _local_web_translations(trans_file):
    messages = []
    try:
        with open(trans_file) as t_file:
            po = babel.messages.pofile.read_po(t_file)
    except Exception:
        return
    for x in po:
        if x.id and x.string and "openerp-web" in x.auto_comments:
            messages.append({'id': x.id, 'string': x.string})
    return messages

def xml2json_from_elementtree(el, preserve_whitespaces=False):
    """ xml2json-direct
    Simple and straightforward XML-to-JSON converter in Python
    New BSD Licensed
    http://code.google.com/p/xml2json-direct/
    """
    res = {}
    if el.tag[0] == "{":
        ns, name = el.tag.rsplit("}", 1)
        res["tag"] = name
        res["namespace"] = ns[1:]
    else:
        res["tag"] = el.tag
    res["attrs"] = {}
    for k, v in el.items():
        res["attrs"][k] = v
    kids = []
    if el.text and (preserve_whitespaces or el.text.strip() != ''):
        kids.append(el.text)
    for kid in el:
        kids.append(xml2json_from_elementtree(kid, preserve_whitespaces))
        if kid.tail and (preserve_whitespaces or kid.tail.strip() != ''):
            kids.append(kid.tail)
    res["children"] = kids
    return res

def binary_content(xmlid=None, model='ir.attachment', id=None, field='datas', unique=False, filename=None, filename_field='datas_fname', download=False, mimetype=None, default_mimetype='application/octet-stream', env=None):
    return request.registry['ir.http'].binary_content(
        xmlid=xmlid, model=model, id=id, field=field, unique=unique, filename=filename, filename_field=filename_field,
        download=download, mimetype=mimetype, default_mimetype=default_mimetype, env=env)

def db_info():
    version_info = openerp.service.common.exp_version()
    return {
        'server_version': version_info.get('server_version'),
        'server_version_info': version_info.get('server_version_info'),
    }


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
    @http.route('/web/redmine/', auth='public', website=True)
    def index(self, **kw):
        # return http.request.render('newpage.index')
        #ensure_db()
        #menu_data = request.registry['ir.ui.menu'].load_menus(request.cr, request.uid, request.debug, context=request.context)
        # return request.render('web.webclient_bootstrap', qcontext={'menu_data': menu_data, 'db_info': json.dumps(db_info())})
        ensure_db()
        menu_data = request.registry['ir.ui.menu'].load_menus(request.cr, request.uid, request.debug, context=request.context)
        return request.render('module_start.redmine_index', qcontext={'menu_data': menu_data, 'db_info': json.dumps(db_info())})
        # return http.request.render('module_start.redmine_index')
        
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