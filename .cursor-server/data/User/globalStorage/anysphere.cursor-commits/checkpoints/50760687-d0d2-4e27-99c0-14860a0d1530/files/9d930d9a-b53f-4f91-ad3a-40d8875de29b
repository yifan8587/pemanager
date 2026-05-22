from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from interfacemanage.models import NetworkInterfaceRecord
from resourcemanage.models import IPAddressEntry
from routemanage.models import DesiredRouteConfig
from routemanage.services.route_kind_map import infer_netplan_device_class_for_interface


class DesiredRouteConfigSerializer(serializers.ModelSerializer):
    ip_address = serializers.IPAddressField(source='ip_allocation.address', read_only=True)
    linked_interface = serializers.SlugRelatedField(
        slug_field='ifname',
        queryset=NetworkInterfaceRecord.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = DesiredRouteConfig
        fields = [
            'id',
            'interface_name',
            'netplan_device_class',
            'linked_interface',
            'dest_cidr',
            'gateway',
            'on_link',
            'metric',
            'route_table',
            'ip_allocation',
            'ip_address',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance: DesiredRouteConfig | None = getattr(self, 'instance', None)

        li = attrs.get('linked_interface', serializers.empty)
        if li is serializers.empty:
            li_resolved = instance.linked_interface if instance else None
        else:
            li_resolved = li

        if li_resolved is not None:
            np = li_resolved.netplan if isinstance(li_resolved.netplan, dict) else None
            attrs['interface_name'] = li_resolved.ifname
            attrs['netplan_device_class'] = infer_netplan_device_class_for_interface(
                netplan_row=np,
                kernel_kind=li_resolved.kind or '',
            )
            attrs['linked_interface'] = li_resolved

        alloc_key = 'ip_allocation' in attrs
        alloc = attrs.get('ip_allocation')
        if not alloc_key and instance:
            alloc = instance.ip_allocation
        elif not alloc_key:
            alloc = None

        if isinstance(alloc, IPAddressEntry) and alloc.interface_code:
            code = alloc.interface_code.strip()
            if not (attrs.get('interface_name') or '').strip() and not li_resolved:
                attrs['interface_name'] = code

        return attrs

    def create(self, validated_data):
        obj = DesiredRouteConfig(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for key, val in validated_data.items():
            setattr(instance, key, val)
        instance.full_clean()
        instance.save()
        return instance


class IPAddressEntryBriefSerializer(serializers.ModelSerializer):
    """供路由表单选择已分配/预留 IP。"""

    customer_code = serializers.CharField(source='customer.code', read_only=True)

    class Meta:
        model = IPAddressEntry
        fields = ['id', 'address', 'state', 'interface_code', 'subnet_label', 'customer_code']
        read_only_fields = ['id', 'address', 'state', 'interface_code', 'subnet_label', 'customer_code']


class ImportSystemRouteItemSerializer(serializers.Serializer):
    """单条内核路由导入为 DesiredRouteConfig。"""

    dst = serializers.CharField(max_length=128)
    gateway = serializers.IPAddressField(required=False, allow_null=True)
    dev = serializers.CharField(max_length=128)
    metric = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    table = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    on_link = serializers.BooleanField(required=False, default=False)


def import_routes_from_live_rows(routes: list[dict]) -> dict:
    created_ids: list[str] = []
    errors: list[dict] = []
    for i, raw in enumerate(routes):
        ser = ImportSystemRouteItemSerializer(data=raw)
        if not ser.is_valid():
            errors.append({'index': i, 'errors': ser.errors})
            continue
        v = ser.validated_data
        dev = v['dev'].strip()
        dst = v['dst'].strip()
        gw = v.get('gateway')
        rec = NetworkInterfaceRecord.objects.filter(ifname=dev).first()
        np = (rec.netplan if rec else None) or {}
        dclass = infer_netplan_device_class_for_interface(
            netplan_row=np if isinstance(np, dict) else None,
            kernel_kind=(rec.kind if rec else 'ethernet'),
        )
        dest_cidr = 'default' if dst.lower() == 'default' else dst
        on_link = bool(v.get('on_link'))
        if gw:
            on_link = False
        try:
            obj = DesiredRouteConfig(
                interface_name=dev,
                netplan_device_class=dclass,
                dest_cidr=dest_cidr,
                gateway=gw,
                on_link=on_link,
                metric=v.get('metric'),
                route_table=v.get('table'),
                linked_interface=rec,
            )
            obj.full_clean()
            obj.save()
            created_ids.append(str(obj.pk))
        except DjangoValidationError as exc:
            errors.append({'index': i, 'errors': exc.message_dict})
        except Exception as exc:  # noqa: BLE001
            errors.append({'index': i, 'errors': str(exc)})
    return {'created_ids': created_ids, 'errors': errors, 'created_count': len(created_ids)}
