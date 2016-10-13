openerp.module_start = function(instance, local) {
    var _t = instance.web._t,
        _lt = instance.web._lt;
    var QWeb = instance.web.qweb;

    instance.web.client_actions.add(
        'redmine.projectlist', 
        'instance.module_start.ProjectList'
    );

    local.ProjectList = instance.web.Widget.extend({
        start: function() {
            console.log("redmine loaded");
        },
    });

    
};