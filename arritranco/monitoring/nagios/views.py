from inventory.models import OperatingSystem
from backups.models import FileBackupTask, R1BackupTask, TSMBackupTask, BackupTask

from django.shortcuts import render_to_response
from django.http import HttpResponse
import logging

logger = logging.getLogger(__name__)

from nsca import NSCA
from models import Service, NagiosCheck, NagiosMachineCheckOpts, NagiosNetworkParent, HUMAN_TO_NAGIOS, \
    NagiosServiceCheckOpts, NagiosUnrackableNetworkedDeviceCheckOpts, NagiosHardwarePolicyCheckOpts, NagiosCheckTemplate
from scheduler.models import TaskStatus, TaskCheck
from templatetags.nagios_filters import nagios_safe
from inventory.models import Machine, PhysicalMachine
from hardware.models import UnrackableNetworkedDevice


def check_templates(request):
    """Return check_templates a.k.a service templates on Nagios conffile."""
    template = 'nagios/check_templates.cfg'
    models_dicts = [x.to_dict() for x in NagiosCheckTemplate.objects.all()]

    context = { 'check_templates': models_dicts }

    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response

def hosts(request):
    """Nagios hosts config file."""
    template = 'nagios/hosts.cfg'

    context = {'machines': [],
               'services': Service.objects.all(),
               'unracknetdevs': UnrackableNetworkedDevice.objects.all()}
    for m in Machine.objects.filter(up=True).order_by('fqdn'):
        context['machines'].append({
            'fqdn': m.fqdn,
            'service_ip': m.get_service_ip(),
            'contact_groups': m.responsibles(),
            'parents': NagiosNetworkParent.get_parents_for_host(m),
        })
    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response


def hosts_ext_info(request):
    """ Nagios extinfo config file """
    l = []
    # FIXME:
    for os in OperatingSystem.objects.filter(type__name__in=['Linux', 'Windows', 'Solaris']):
        running_machines = os.machine_set.filter(up=True)
        if running_machines.count():
            machines = []
            for m in running_machines:
                # FIXME: We need to import ip's from the old tool to improve this a little bit.
                #                if m.maquinared_set.filter(visible = True).count():
                #                    machines.append(m)
                machines.append(m)
            if len(machines):
                l.append((os.logo, ",".join([m.fqdn for m in machines])))
    context = {"logo_machines": l}
    return render_to_response('nagios/host_ext_info.cfg', context, mimetype="text/plain")


def get_checks(request, name):
    """Returns config file with asigned 'name' checks."""
    template = 'nagios/check.cfg'
    context = {
        'checks_machine': NagiosMachineCheckOpts.objects.filter(check=NagiosCheck.objects.filter(name=name),
                                                                machine__up=True),
        'checks_unracknetdev': NagiosUnrackableNetworkedDeviceCheckOpts.objects.filter(
            check=NagiosCheck.objects.filter(name=name))
    }
    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response


def backup_checks(request):
    """ Backup checks """
    template = 'nagios/backup_checks.cfg'
    context = {
        'backup_file_tasks': FileBackupTask.objects.filter(machine__up=True).filter(active=True).order_by(
            'machine__fqdn'),
        'r1soft_tasks': R1BackupTask.objects.filter(machine__up=True).filter(active=True).order_by('machine__fqdn'),
        'TSM_tasks': TSMBackupTask.objects.filter(machine__up=True).filter(active=True).order_by('machine__fqdn')}
    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response

#FIXME: Refactor to look at last_run task. Otherwise it will silently fail if no task
#was executed.
def refresh_nagios_status(request):
    """Syncs last task status on database to Nagios using NSCA."""
    logger.debug('Refreshing nagios status')
    nsca = NSCA()
    for bt in BackupTask.objects.filter(active=True, machine__up=True):
        try:
            tch = TaskCheck.objects.filter(task=bt).order_by('-task_time')[0]
        except IndexError:
            logger.debug('There is no TaskCheck for %s', bt)
            continue
        status = tch.last_status
        if isinstance(status, TaskStatus):
            logger.debug('Last status for %s: %s is %s (%s)', bt, bt.description, status, status.check_time)
            logger.debug('Human to nagios de %s es %d' % (status.status, HUMAN_TO_NAGIOS[status.status]))
            nsca.add_custom_status(
                bt.machine.fqdn,
                nagios_safe(bt.description),
                HUMAN_TO_NAGIOS[status.status],
                status.comment
            )
    nsca.send()
    logger.debug('Nagios status updated for %s', bt)

    return HttpResponse("Nagios up to date")


def getchecks_all(request):
    template = 'nagios/check.cfg'
    context = {
        'checks_machine': NagiosMachineCheckOpts.objects.filter(machine__up=True),
        'checks_unracknetdev': NagiosUnrackableNetworkedDeviceCheckOpts.objects.all()
    }

    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response


def hardware(request):
    template = 'nagios/hardware_checks.cfg'
    checks = []
    for HardwarePolicy in NagiosHardwarePolicyCheckOpts.objects.all():
        for hwmodel in HardwarePolicy.hwmodel.all():
            for machine in PhysicalMachine.objects.filter(server__model__id=hwmodel.id, up=True).exclude(
                    os__in=HardwarePolicy.excluded_os.all()):

                if HardwarePolicy.get_full_check().__contains__("management_ip"):
                    if machine.get_management_ip() is not None \
                            and not HardwarePolicy.excluded_ips.filter(addr=machine.get_management_ip()):
                        checks.append({"check": HardwarePolicy.check,
                                       "host_name": machine.fqdn,
                                       "hwpolicy": HardwarePolicy,
                                       "command": HardwarePolicy.get_full_check() % {"management_ip": machine.server.management_ip.addr}
                                       }
                                      )

                else:
                    if not HardwarePolicy.excluded_ips.\
                            filter(addr__in=[ip.addr for ip in machine.get_all_ips()]):
                        checks.append({"check": HardwarePolicy.check,
                                       "host_name": machine.fqdn,
                                       "hwpolicy": HardwarePolicy,
                                       "command": HardwarePolicy.get_full_check() % {"fqdn": machine.fqdn}
                                       }
                                      )

            for device in UnrackableNetworkedDevice.objects.filter(model=hwmodel):
                if not HardwarePolicy.excluded_ips.filter(addr=device.main_ip.addr):
                    checks.append({"check": HardwarePolicy.check,
                                   "host_name": device.name,
                                   "hwpolicy": HardwarePolicy,
                                   "command": HardwarePolicy.get_full_check() % {
                                       "management_ip": device.main_ip.addr}
                                   }
                                  )

    context = {"checks": checks}

    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response


def service(request):
    template = 'nagios/service_checks.cfg'

    checks_service_machine = []
    for serviceCheck in NagiosServiceCheckOpts.objects.all():
        for machine in serviceCheck.service.machines.all():
            if machine.up and not NagiosMachineCheckOpts.objects.filter(machine=machine, check=serviceCheck.check):
                if not [i for i in checks_service_machine if i["description"] == serviceCheck.check.description and i["name"] == machine.fqdn]:
                    checks_service_machine.append({"check":serviceCheck.check,
                                                   "description": serviceCheck.check.description,
                                                   "name": machine.fqdn,
                                                   "command": serviceCheck.get_full_check(),
                                                   "contact_groups": serviceCheck.contact_group_all_csv})
    context = {
        'checks_service': NagiosServiceCheckOpts.objects.all(),
        'checks_service_machine': checks_service_machine,
    }

    if 'file' in request.GET:
        response = render_to_response(template, context, mimetype="text/plain")
        response['Content-Disposition'] = 'attachment; filename=%s' % request.GET['file']
    else:
        response = render_to_response(template, context, mimetype="text/plain")
    return response
