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
            selfInstance = this;
            jQuery.ajax({
                type: "post",
                url: '/web/redmine/project',
                dataType: 'json',
                async: true,
                data: {
                    'csrf_token': odooGlobalRkRedmine.token
                },
                success: function ( data ) {
                    if (data.success != 1) {
                        return false;
                    }
                    if (typeof data.data == 'undefined' || !data.data) {
                        return false;
                    }
                    selfInstance.$el.append(QWeb.render("RedmineProject", {
                        data: data.data,
                    }));
                },
                failure: function( data ){}
            });
        },
    });

    
};
