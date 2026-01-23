from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import InstallBase, Product, Customer, ExpansionHistory, ClusterSwitch, SwitchModel, Issue, RMA, Part, NetAppAPIConfig, UserProfile
from django.utils import timezone
from datetime import timedelta, datetime
from .forms import InstallBaseForm, ClusterSwitchForm, SwitchModelForm, IssueForm, RMAForm, PartForm
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Min, Case, When, IntegerField
from django.views.generic.edit import UpdateView
from django.urls import reverse_lazy
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator 
from django.db.models.functions import Concat
import datetime
import requests
import json
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@login_required
def installbase_list(request):
    query = request.GET.get('q', '')
    # 삭제되지 않은 장비만 필터링 (customer와 product를 미리 로드)
    base_queryset = InstallBase.objects.filter(deleted_at__isnull=True).select_related('customer', 'product')

    if query:
        # annotate를 사용하는 쿼리와 사용하지 않는 쿼리를 분리
        # 1. 일반 필드 검색 (annotate 없이)
        general_query = base_queryset.filter(
            Q(customer__name__icontains=query) |
            Q(cluster_name__icontains=query) |
            Q(serial_number_1__icontains=query) |
            Q(serial_number_2__icontains=query) |
            Q(location__icontains=query) |
            Q(service_name__icontains=query) |
            Q(project__icontains=query) |
            Q(product__model_name__icontains=query) |
            Q(node_name_1__icontains=query) |
            Q(node_name_2__icontains=query) |
            Q(ontap_version__icontains=query) |
            Q(periodic_inspection__icontains=query) |
            Q(license_type__icontains=query) |
            Q(cluster_mgmt_ip__icontains=query) |
            Q(node1_mgmt_ip__icontains=query) |
            Q(node2_mgmt_ip__icontains=query) |
            Q(node1_bmc_ip__icontains=query) |
            Q(node2_bmc_ip__icontains=query) |
            Q(other_ips__icontains=query) |
            Q(shelf_models__icontains=query)
        )
        
        # 2. 엔지니어 관련 검색 (ManyToMany 관계, distinct 필요)
        engineer_query = base_queryset.filter(
            Q(assigned_engineers__username__icontains=query) |
            Q(assigned_engineers__first_name__icontains=query) |
            Q(assigned_engineers__last_name__icontains=query)
        ).distinct()
        
        # 3. 성+이름 검색 (annotate 사용, distinct 필요)
        full_name_query = base_queryset.annotate(
            full_name=Concat('assigned_engineers__last_name', 'assigned_engineers__first_name')
        ).filter(full_name__icontains=query).distinct()
        
        # 각 쿼리의 ID를 가져와서 합치기
        general_ids = set(general_query.values_list('id', flat=True))
        engineer_ids = set(engineer_query.values_list('id', flat=True))
        full_name_ids = set(full_name_query.values_list('id', flat=True))
        
        # 모든 ID 합치기
        all_ids = general_ids | engineer_ids | full_name_ids
        
        # 최종 쿼리 생성
        filtered_queryset = base_queryset.filter(id__in=all_ids)
    else:
        filtered_queryset = base_queryset

    # cluster_name별로 그룹화하여 첫 번째 노드만 가져오기
    # 성능 최적화: 한 번의 쿼리로 모든 데이터 가져오기
    
    # 각 cluster_name의 첫 번째 노드 ID 가져오기 (최적화된 쿼리)
    first_node_ids = filtered_queryset.values('cluster_name').annotate(
        first_id=Min('id')
    ).values_list('first_id', flat=True)
    
    # 첫 번째 노드들만 한 번에 가져오기
    first_nodes = filtered_queryset.filter(id__in=first_node_ids).select_related('customer', 'product')
    
    # 각 cluster_name의 모든 노드 데이터를 한 번에 가져오기 (집계용)
    cluster_data = defaultdict(lambda: {
        'model_names': set(),
        'serial_numbers': set(),
        'device_count': 0
    })
    
    # 모든 노드의 필요한 데이터만 한 번에 가져오기
    all_cluster_data = filtered_queryset.values('cluster_name', 'product__model_name', 'serial_number_1', 'serial_number_2')
    
    for item in all_cluster_data:
        cluster_name = item['cluster_name']
        cluster_data[cluster_name]['device_count'] += 1
        if item['product__model_name']:
            cluster_data[cluster_name]['model_names'].add(item['product__model_name'])
        if item['serial_number_1'] and item['serial_number_1'].strip():
            cluster_data[cluster_name]['serial_numbers'].add(item['serial_number_1'])
        if item['serial_number_2'] and item['serial_number_2'].strip():
            cluster_data[cluster_name]['serial_numbers'].add(item['serial_number_2'])
    
    # 첫 번째 노드에 집계 데이터 추가
    object_list = []
    for node in first_nodes:
        cluster_name = node.cluster_name
        data = cluster_data.get(cluster_name, {'model_names': set(), 'serial_numbers': set(), 'device_count': 0})
        node_count = data['device_count'] * 2
        model_names = sorted(list(data['model_names']))
        serial_numbers = sorted(list(data['serial_numbers']))
        
        setattr(node, 'cluster_node_count', node_count)
        setattr(node, 'is_multi_node', node_count >= 4)
        setattr(node, 'cluster_model_names', model_names)
        setattr(node, 'cluster_serial_numbers', serial_numbers)
        object_list.append(node)

    # 정렬 파라미터 처리
    sort_col = request.GET.get('sort_col')
    sort_order = request.GET.get('sort_order', 'desc')  # 기본값: 내림차순
    
    if sort_col:
        try:
            sort_col = int(sort_col)
            # 정렬 기준에 따라 정렬
            if sort_col == 0:  # Customer
                object_list = sorted(object_list, 
                    key=lambda x: x.customer.name if x.customer else '', 
                    reverse=(sort_order == 'desc'))
            elif sort_col == 1:  # System Info (cluster_name)
                object_list = sorted(object_list, 
                    key=lambda x: x.cluster_name or '', 
                    reverse=(sort_order == 'desc'))
            elif sort_col == 4:  # Contract End
                object_list = sorted(object_list, 
                    key=lambda x: x.contract_end_date if x.contract_end_date else datetime.date(1900, 1, 1), 
                    reverse=(sort_order == 'desc'))
            else:
                # 기본 정렬 (id)
                object_list = sorted(object_list, key=lambda x: x.id, reverse=True)
        except (ValueError, TypeError):
            # 기본 정렬 (id)
            object_list = sorted(object_list, key=lambda x: x.id, reverse=True)
    else:
        # 기본 정렬 (id)
        object_list = sorted(object_list, key=lambda x: x.id, reverse=True)

    # 페이지네이션 기능 구현 (페이지당 10개)
    paginator = Paginator(object_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 템플릿에 전달 (installbases 변수에 page_obj를 할당하여 기존 템플릿 호환 유지)
    return render(request, 'installbase_list.html', {
        'installbases': page_obj,      # 기존 for문 호환
        'page_obj': page_obj,          # 페이지네이션 컨트롤용
        'is_paginated': page_obj.has_other_pages(), # 페이지가 2페이지 이상인지 여부
        'query': query,
        'sort_col': sort_col,
        'sort_order': sort_order
    })


@login_required
def installbase_create(request):
    periodic_choices = [
        ('none', '정기점검 비대상'),
        ('monthly', '월 점검'),
        ('quarter', '분기 점검'),
        ('half', '반기 점검'),
    ]

    if request.method == "POST":
        form = InstallBaseForm(request.POST, request.FILES)
        if form.is_valid():
            new_ib = form.save(commit=False)

            # 라디오 버튼 값 매핑
            switch_type = request.POST.get('switch_type')
            new_ib.is_switch_connected = (switch_type == 'switched')

            # 1. 먼저 DB에 본체를 저장 (이때 ID가 생성됨)
            new_ib.save()

            # 2. ManyToMany(엔지니어) 관계 저장
            form.save_m2m()

            # 3. [수정됨] 생성된 객체의 pk를 사용하여 상세 페이지로 이동
            return redirect('installbase_detail', pk=new_ib.pk)
        else:
            print("❌ Form Validation Errors:", form.errors)
    else:
        form = InstallBaseForm()
        # 엔지니어 이름을 성+이름으로 표시하도록 수정 (활성화된 유저만)
        User = get_user_model()
        form.fields['assigned_engineers'].choices = [
            (u.id, f"{u.last_name}{u.first_name}") for u in User.objects.filter(is_active=True)
        ]

    context = {
        'form': form,
        'title': '신규 스토리지 등록',
        'periodic_choices': periodic_choices,
    }
    return render(request, 'installbase_form.html', context)

# --- AJAX 로직 (기존 유지) ---

def add_customer_ajax(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name')
            logo = request.FILES.get('logo')
            if name:
                customer = Customer.objects.create(name=name, logo=logo)
                logo_url = customer.logo.url if customer.logo else None
                return JsonResponse({
                    'id': customer.id, 
                    'name': customer.name,
                    'logo_url': logo_url
                })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def add_product_ajax(request):
    if request.method == "POST":
        try:
            lineup = request.POST.get('lineup')
            model_name = request.POST.get('model_name')
            image = request.FILES.get('image')

            if model_name:
                product = Product.objects.create(
                    lineup=lineup,
                    model_name=model_name,
                    image=image
                )
                return JsonResponse({'id': product.id, 'name': str(product)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def get_image_url(request):
    item_type = request.GET.get('type')
    item_id = request.GET.get('id')
    try:
        if item_type == 'customer':
            obj = Customer.objects.get(id=item_id)
            url = obj.logo.url if obj.logo else None
        else:
            obj = Product.objects.get(id=item_id)
            url = obj.image.url if obj.image else None
        return JsonResponse({'url': url})
    except:
        return JsonResponse({'url': None})


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def update_avatar(request):
    """사용자 아바타 시드 업데이트"""
    try:
        data = json.loads(request.body)
        seed = data.get('seed', '').strip()
        
        if not seed:
            return JsonResponse({'success': False, 'error': '시드 값이 필요합니다.'}, status=400)
        
        # UserProfile 가져오기 또는 생성
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.avatar_seed = seed
        profile.save()
        
        return JsonResponse({'success': True, 'avatar_url': profile.get_avatar_url()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_available_node_numbers(request):
    """클러스터 이름으로 사용 가능한 노드 번호 조회"""
    cluster_name = request.GET.get('cluster_name', '').strip()
    exclude_node1 = request.GET.get('exclude_node1', '')
    exclude_node2 = request.GET.get('exclude_node2', '')
    
    if not cluster_name:
        return JsonResponse({'available_numbers': list(range(1, 41))})
    
    # 해당 클러스터에 등록된 모든 노드 번호 조회 (삭제되지 않은 것만)
    used_numbers = set()
    cluster_devices = InstallBase.objects.filter(
        cluster_name=cluster_name,
        deleted_at__isnull=True
    )
    
    for device in cluster_devices:
        if device.node_number_1:
            used_numbers.add(device.node_number_1)
        if device.node_number_2:
            used_numbers.add(device.node_number_2)
    
    # 현재 선택된 노드 번호는 제외 (다른 노드에서 선택 가능하도록)
    if exclude_node1:
        try:
            used_numbers.discard(int(exclude_node1))
        except:
            pass
    if exclude_node2:
        try:
            used_numbers.discard(int(exclude_node2))
        except:
            pass
    
    # 사용 가능한 노드 번호 (1-40 중 사용되지 않은 것)
    all_numbers = set(range(1, 41))
    available_numbers = sorted(list(all_numbers - used_numbers))
    
    return JsonResponse({'available_numbers': available_numbers})


@login_required
def installbase_detail(request, pk):
    # 장비 상세 정보 가져오기 (없으면 404 에러) - 최적화: select_related 사용
    installbase = get_object_or_404(
        InstallBase.objects.select_related(
            'customer', 'product', 'cluster_switch', 
            'cluster_switch__switch_model_1', 'cluster_switch__switch_model_2',
            'fabric_pool_switch', 'fabric_pool_switch__switch_model_1', 'fabric_pool_switch__switch_model_2'
        ).prefetch_related('assigned_engineers'),
        pk=pk
    )
    
    # 같은 cluster_name을 가진 모든 노드들 가져오기 (삭제되지 않은 것만)
    # cluster_name이 빈 문자열이거나 None인 경우를 처리
    if installbase.cluster_name:
        # DB에서 정렬하도록 최적화 (Python 정렬보다 빠름)
        from django.db.models import Case, When, IntegerField
        all_cluster_nodes = InstallBase.objects.filter(
            cluster_name=installbase.cluster_name,
            deleted_at__isnull=True
        ).select_related(
            'product', 'customer', 'cluster_switch', 
            'cluster_switch__switch_model_1', 'cluster_switch__switch_model_2',
            'fabric_pool_switch', 'fabric_pool_switch__switch_model_1', 'fabric_pool_switch__switch_model_2'
        ).prefetch_related('assigned_engineers').annotate(
            # node_number_1이 None인 경우 999로 처리하여 뒤로 보냄
            sort_node_1=Case(
                When(node_number_1__isnull=True, then=999),
                default='node_number_1',
                output_field=IntegerField()
            ),
            sort_node_2=Case(
                When(node_number_2__isnull=True, then=999),
                default='node_number_2',
                output_field=IntegerField()
            )
        ).order_by('sort_node_1', 'sort_node_2', 'id')
    else:
        # cluster_name이 없는 경우 현재 노드만
        all_cluster_nodes = [installbase]
    
    # 멀티노드 여부 판단 (4노드 이상 = 2개 이상의 InstallBase 레코드)
    # QuerySet인 경우 count() 사용 (더 효율적)
    if isinstance(all_cluster_nodes, list):
        is_multi_node = len(all_cluster_nodes) >= 2
    else:
        is_multi_node = all_cluster_nodes.count() >= 2
    
    # 증설 이력 가져오기 (최적화: select_related 사용)
    if is_multi_node and installbase.cluster_name:
        # 멀티노드 클러스터일 때: 클러스터 전체 노드의 이력을 가져오기 (날짜 내림차순)
        if isinstance(all_cluster_nodes, list):
            node_ids = [node.pk for node in all_cluster_nodes]
        else:
            node_ids = list(all_cluster_nodes.values_list('pk', flat=True))
        expansions = ExpansionHistory.objects.filter(install_base_id__in=node_ids).select_related('install_base').order_by('-expansion_date')
    else:
        # 일반 클러스터일 때: 현재 노드의 이력만 가져오기
        expansions = installbase.expansions.select_related('install_base').all().order_by('-expansion_date')
    
    # 총 노드 수 계산 (각 InstallBase 레코드는 2개의 노드를 나타냄)
    if isinstance(all_cluster_nodes, list):
        total_node_count = len(all_cluster_nodes) * 2
        cluster_members = [node for node in all_cluster_nodes if node.pk != pk]
    else:
        total_node_count = all_cluster_nodes.count() * 2
        cluster_members = all_cluster_nodes.exclude(pk=pk)
    
    # 멀티노드일 때 노드 정보를 JSON으로 직렬화
    import json
    nodes_data = []
    if is_multi_node:
        for node in all_cluster_nodes:
            # 노드 번호 계산 (node_number_1이 있으면 사용, 없으면 순서대로)
            node_num = node.node_number_1 if node.node_number_1 is not None else None
            # product 이미지 URL
            product_image_url = ''
            if node.product and node.product.image:
                product_image_url = node.product.image.url
            
            nodes_data.append({
                'pk': node.pk,
                'node_number_1': node.node_number_1,
                'node_number_2': node.node_number_2,
                'node_name_1': node.node_name_1 or '',
                'node_name_2': node.node_name_2 or '',
                'serial_number_1': node.serial_number_1 or '',
                'serial_number_2': node.serial_number_2 or '',
                'product_model_name': node.product.model_name if node.product else '',
                'product_image_url': product_image_url,
                'ontap_version': node.ontap_version or '',
                'license_type': node.license_type or '',
                'service_level': node.service_level or '',
                'service_level_display': node.get_service_level_display(),
                'periodic_inspection': node.periodic_inspection or '',
                'periodic_inspection_display': node.get_periodic_inspection_display(),
                'project': node.project or '',
                'controller_slots': node.controller_slots or '',
                'is_switch_connected': node.is_switch_connected,
                'cluster_switch_name_1': node.cluster_switch.switch_name_1 if node.cluster_switch and node.cluster_switch.switch_name_1 else '',
                'cluster_switch_name_2': node.cluster_switch.switch_name_2 if node.cluster_switch and node.cluster_switch.switch_name_2 else '',
                'cluster_switch_model_1': node.cluster_switch.switch_model_1.model_name if node.cluster_switch and node.cluster_switch.switch_model_1 else '',
                'cluster_switch_model_2': node.cluster_switch.switch_model_2.model_name if node.cluster_switch and node.cluster_switch.switch_model_2 else '',
                'cluster_switch_serial_1': node.cluster_switch.serial_number_1 if node.cluster_switch and node.cluster_switch.serial_number_1 else '',
                'cluster_switch_serial_2': node.cluster_switch.serial_number_2 if node.cluster_switch and node.cluster_switch.serial_number_2 else '',
                'cluster_switch_ip_1': str(node.cluster_switch.ip_address_1) if node.cluster_switch and node.cluster_switch.ip_address_1 else '',
                'cluster_switch_ip_2': str(node.cluster_switch.ip_address_2) if node.cluster_switch and node.cluster_switch.ip_address_2 else '',
                'cluster_switch_front_image_1': node.cluster_switch.switch_model_1.front_image.url if node.cluster_switch and node.cluster_switch.switch_model_1 and node.cluster_switch.switch_model_1.front_image else '',
                'cluster_switch_back_image_1': node.cluster_switch.switch_model_1.back_image.url if node.cluster_switch and node.cluster_switch.switch_model_1 and node.cluster_switch.switch_model_1.back_image else '',
                'cluster_switch_front_image_2': node.cluster_switch.switch_model_2.front_image.url if node.cluster_switch and node.cluster_switch.switch_model_2 and node.cluster_switch.switch_model_2.front_image else '',
                'cluster_switch_back_image_2': node.cluster_switch.switch_model_2.back_image.url if node.cluster_switch and node.cluster_switch.switch_model_2 and node.cluster_switch.switch_model_2.back_image else '',
                'is_fabric_pool_connected': node.is_fabric_pool_connected,
                'fabric_pool_switch_name_1': node.fabric_pool_switch.switch_name_1 if node.fabric_pool_switch and node.fabric_pool_switch.switch_name_1 else '',
                'fabric_pool_switch_name_2': node.fabric_pool_switch.switch_name_2 if node.fabric_pool_switch and node.fabric_pool_switch.switch_name_2 else '',
                'fabric_pool_switch_model_1': node.fabric_pool_switch.switch_model_1.model_name if node.fabric_pool_switch and node.fabric_pool_switch.switch_model_1 else '',
                'fabric_pool_switch_model_2': node.fabric_pool_switch.switch_model_2.model_name if node.fabric_pool_switch and node.fabric_pool_switch.switch_model_2 else '',
                'fabric_pool_switch_serial_1': node.fabric_pool_switch.serial_number_1 if node.fabric_pool_switch and node.fabric_pool_switch.serial_number_1 else '',
                'fabric_pool_switch_serial_2': node.fabric_pool_switch.serial_number_2 if node.fabric_pool_switch and node.fabric_pool_switch.serial_number_2 else '',
                'fabric_pool_switch_ip_1': str(node.fabric_pool_switch.ip_address_1) if node.fabric_pool_switch and node.fabric_pool_switch.ip_address_1 else '',
                'fabric_pool_switch_ip_2': str(node.fabric_pool_switch.ip_address_2) if node.fabric_pool_switch and node.fabric_pool_switch.ip_address_2 else '',
                'fabric_pool_switch_front_image_1': node.fabric_pool_switch.switch_model_1.front_image.url if node.fabric_pool_switch and node.fabric_pool_switch.switch_model_1 and node.fabric_pool_switch.switch_model_1.front_image else '',
                'fabric_pool_switch_back_image_1': node.fabric_pool_switch.switch_model_1.back_image.url if node.fabric_pool_switch and node.fabric_pool_switch.switch_model_1 and node.fabric_pool_switch.switch_model_1.back_image else '',
                'fabric_pool_switch_front_image_2': node.fabric_pool_switch.switch_model_2.front_image.url if node.fabric_pool_switch and node.fabric_pool_switch.switch_model_2 and node.fabric_pool_switch.switch_model_2.front_image else '',
                'fabric_pool_switch_back_image_2': node.fabric_pool_switch.switch_model_2.back_image.url if node.fabric_pool_switch and node.fabric_pool_switch.switch_model_2 and node.fabric_pool_switch.switch_model_2.back_image else '',
                'cluster_mgmt_ip': node.cluster_mgmt_ip or '',
                'country': node.country or '',
                'country_display': node.get_country_display() or '',
                'location': node.location or '',
                'rack_space': node.rack_space or '',
                'shelf_models': node.shelf_models or '',
                'disk_info': node.disk_info or '',
                'ip_lists': node.ip_lists or '',
                'cluster_mgmt_ip': node.cluster_mgmt_ip or '',
                'node1_mgmt_ip': node.node1_mgmt_ip or '',
                'node2_mgmt_ip': node.node2_mgmt_ip or '',
                'node1_bmc_ip': node.node1_bmc_ip or '',
                'node2_bmc_ip': node.node2_bmc_ip or '',
                'other_ips': node.other_ips or '',
                'install_date': node.install_date.strftime('%Y-%m-%d') if node.install_date else '',
                'contract_end_date': node.contract_end_date.strftime('%Y-%m-%d') if node.contract_end_date else '',
                'maintenance_start': node.maintenance_start.strftime('%Y-%m-%d') if node.maintenance_start else '',
                'maintenance_end': node.maintenance_end.strftime('%Y-%m-%d') if node.maintenance_end else '',
                'assigned_engineers': [{'username': e.username, 'last_name': e.last_name or '', 'first_name': e.first_name or ''} for e in node.assigned_engineers.all()],
            })
    
    context = {
        'installbase': installbase,
        'expansions': expansions,
        'cluster_members': cluster_members,  # 다른 노드들 (기존 호환성)
        'all_cluster_nodes': all_cluster_nodes,  # 모든 노드 (현재 노드 포함)
        'is_multi_node': is_multi_node,
        'total_node_count': total_node_count,  # 총 노드 수
        'nodes_data_json': json.dumps(nodes_data),  # JSON 데이터
    }
    return render(request, 'installbase_detail.html', context)


def add_expansion_ajax(request, pk):
    if request.method == "POST":
        install_base = get_object_or_404(InstallBase, pk=pk)
        date_val = request.POST.get('date')
        desc_val = request.POST.get('description')
        node_id = request.POST.get('node_id')  # 멀티노드 클러스터일 때 선택한 노드 ID

        if date_val and desc_val:
            # 멀티노드 클러스터일 때는 선택한 노드 ID를 사용, 아니면 현재 노드 사용
            target_install_base = install_base
            if node_id:
                # 같은 클러스터 내의 노드인지 확인
                target_install_base = get_object_or_404(InstallBase, pk=node_id, cluster_name=install_base.cluster_name, deleted_at__isnull=True)
            
            # 1. DB에 저장
            expansion = ExpansionHistory.objects.create(
                install_base=target_install_base,
                expansion_date=date_val,
                description=desc_val
            )

            # 2. [수정됨] 에러 방지를 위해 날짜를 문자열 그대로 반환하거나
            # 모델 인스턴스에서 직접 처리하는 대신 입력받은 형식을 활용합니다.
            return JsonResponse({
                'status': 'success',
                'id': expansion.id,
                'date': date_val, # 이미 YYYY-MM-DD 형식이므로 그대로 전달
                'description': expansion.description,
                'node_name_1': target_install_base.node_name_1 or '',
                'node_name_2': target_install_base.node_name_2 or '',
                'serial_number_1': target_install_base.serial_number_1,
                'serial_number_2': target_install_base.serial_number_2 or ''
            })
    return JsonResponse({'status': 'fail'}, status=400)

def edit_expansion_ajax(request, pk):
    if request.method == "POST":
        expansion = get_object_or_404(ExpansionHistory, pk=pk)
        date_val = request.POST.get('date')
        desc_val = request.POST.get('description')

        if date_val and desc_val:
            expansion.expansion_date = date_val
            expansion.description = desc_val
            expansion.save()
            return JsonResponse({
                'status': 'success',
                'date': date_val,
                'description': expansion.description,
                'node_name_1': expansion.install_base.node_name_1 or '',
                'node_name_2': expansion.install_base.node_name_2 or '',
                'serial_number_1': expansion.install_base.serial_number_1,
                'serial_number_2': expansion.install_base.serial_number_2 or ''
            })
    return JsonResponse({'status': 'fail'}, status=400)

def delete_expansion_ajax(request, pk):
    if request.method == "POST":
        expansion = get_object_or_404(ExpansionHistory, pk=pk)
        expansion.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'fail'}, status=400)

@login_required
def dashboard(request):
    # 1. 전체 장비 수량 (삭제된 것 포함)
    total_storage_count = InstallBase.objects.count()
    
    # 2. 활성화된 스토리지 수량 (삭제되지 않은 장비만)
    active_installbases = InstallBase.objects.filter(deleted_at__isnull=True)
    active_storage_count = active_installbases.count()
    
    # 3. 진행 중인 이슈 수량
    open_issues_count = Issue.objects.filter(
        deleted_at__isnull=True,
        status__in=['진행중']
    ).count()
    
    # 4. 반납 되지 않은 RMA 수량
    not_returned_rma_count = RMA.objects.filter(
        deleted_at__isnull=True,
        return_status__in=['not_returned', 'not_required']
    ).count()
    
    # 5. 최근 1주일 내 발생한 이슈
    one_week_ago = timezone.now() - timedelta(days=7)
    recent_issues = Issue.objects.filter(
        deleted_at__isnull=True,
        issue_date__gte=one_week_ago
    ).order_by('-issue_date')
    
    # 6. 고객사별 장비 대수 (TOP 5, 나머지는 Other)
    customer_stats = (
        active_installbases
        .values('customer__name')
        .annotate(count=Count('customer__name'))
        .order_by('-count')
    )
    customer_list = [(item['customer__name'], item['count']) for item in customer_stats if item['customer__name']]
    
    if len(customer_list) > 5:
        top5_customers = customer_list[:5]
        other_count = sum(count for _, count in customer_list[5:])
        customer_labels = [name for name, _ in top5_customers] + ['Other']
        customer_data = [count for _, count in top5_customers] + [other_count]
    else:
        customer_labels = [name for name, _ in customer_list]
        customer_data = [count for _, count in customer_list]
    
    # 7. 장비 모델 분포 차트 (TOP 10, 나머지는 Other)
    model_stats = (
        active_installbases
        .values('product__model_name')
        .annotate(count=Count('product__model_name'))
        .order_by('-count')
    )
    model_list = [(item['product__model_name'], item['count']) for item in model_stats if item['product__model_name']]
    
    if len(model_list) > 10:
        top10_models = model_list[:10]
        other_count = sum(count for _, count in model_list[10:])
        chart_labels = [name for name, _ in top10_models] + ['Other']
        chart_data = [count for _, count in top10_models] + [other_count]
    else:
        chart_labels = [name for name, _ in model_list]
        chart_data = [count for _, count in model_list]
    
    # 8. 글로벌 장비 배치 현황 (국가별)
    country_stats = active_installbases.values('country').annotate(count=Count('country')).order_by('-count')
    country_labels = [item['country'] for item in country_stats]
    country_data = [item['count'] for item in country_stats]
    
    # 국가 코드를 국가명으로 변환
    country_name_map = {
        'KR': 'South Korea',
        'US': 'United States',
        'CN': 'China',
        'DE': 'Germany',
        'SK': 'Slovakia',
        'IN': 'India',
        'SG': 'Singapore',
    }
    country_display_labels = [country_name_map.get(code, code) for code in country_labels]

    context = {
        'total_storage_count': total_storage_count,
        'active_storage_count': active_storage_count,
        'open_issues_count': open_issues_count,
        'not_returned_rma_count': not_returned_rma_count,
        'recent_issues': recent_issues,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'country_labels': country_display_labels,
        'country_data': country_data,
        'customer_labels': customer_labels,
        'customer_data': customer_data,
    }
    return render(request, 'dashboard.html', context)


class InstallBaseUpdateView(UpdateView):
    model = InstallBase
    fields = '__all__'
    template_name = 'installbase_update.html'

    def get_form(self, form_class=None):
        """폼 생성 시 엔지니어 리스트를 아이디가 아닌 이름으로 표시하도록 수정"""
        form = super().get_form(form_class)
        User = get_user_model()

        # choices를 (ID, '성과 이름') 튜플 리스트로 재구성 (활성화된 유저만)
        form.fields['assigned_engineers'].choices = [
            (u.id, f"{u.last_name}{u.first_name}") for u in User.objects.filter(is_active=True)
        ]
        return form

    def get_context_data(self, **kwargs):
        """템플릿에서 이미 선택된 엔지니어를 구분할 수 있도록 ID 리스트 전달"""
        context = super().get_context_data(**kwargs)

        # 현재 이 장비(InstallBase)에 할당된 엔지니어들의 ID만 추출하여 리스트로 만듦
        assigned_ids = self.object.assigned_engineers.values_list('id', flat=True)
        context['current_engineer_ids'] = list(assigned_ids)

        return context
    
    def get_success_url(self):
        """수정 완료 후 상세 페이지로 이동"""
        return reverse_lazy('installbase_detail', kwargs={'pk': self.object.pk})


@login_required
def installbase_delete(request, pk):
    """장비 삭제 처리 (soft delete)"""
    installbase = get_object_or_404(InstallBase, pk=pk)
    
    if request.method == "POST":
        # soft delete: deleted_at 필드에 현재 시간을 설정
        installbase.deleted_at = timezone.now()
        installbase.save()
        return redirect('installbase_list')
    
    # GET 요청의 경우 상세 페이지로 리다이렉트
    return redirect('installbase_detail', pk=pk)


@login_required
def installbase_restore(request, pk):
    """장비 삭제 취소 처리 (복구)"""
    installbase = get_object_or_404(InstallBase, pk=pk)
    
    if request.method == "POST":
        # 삭제 취소: deleted_at 필드를 None으로 설정
        installbase.deleted_at = None
        installbase.save()
        return redirect('installbase_detail', pk=pk)
    
    # GET 요청의 경우 상세 페이지로 리다이렉트
    return redirect('installbase_detail', pk=pk)


@login_required
def installbase_deleted_list(request):
    """삭제된 장비 목록 조회"""
    query = request.GET.get('q', '')
    # 삭제된 장비만 필터링
    base_queryset = InstallBase.objects.filter(deleted_at__isnull=False)
    
    if query:
        object_list = base_queryset.filter(
            Q(customer__name__icontains=query) |
            Q(cluster_name__icontains=query) |
            Q(serial_number_1__icontains=query)
        ).order_by('-deleted_at')
    else:
        object_list = base_queryset.order_by('-deleted_at')

    return render(request, 'installbase_deleted_list.html', {
        'installbases': object_list,
        'query': query
    })

# ClusterSwitch 관련 뷰
@login_required
def clusterswitch_list(request):
    """클러스터 스위치 목록"""
    query = request.GET.get('q', '')
    base_queryset = ClusterSwitch.objects.filter(deleted_at__isnull=True).select_related(
        'switch_model_1', 'switch_model_2'
    )
    
    # 필터 처리
    filter_0_text = request.GET.get('filter_0_text', '')
    filter_0_op = request.GET.get('filter_0_op', 'contains')
    filter_1_text = request.GET.get('filter_1_text', '')
    filter_1_op = request.GET.get('filter_1_op', 'contains')
    filter_2_text = request.GET.get('filter_2_text', '')
    filter_2_op = request.GET.get('filter_2_op', 'contains')
    
    if filter_0_text:  # Switch #1 필터
        if filter_0_op == 'contains':
            base_queryset = base_queryset.filter(switch_name_1__icontains=filter_0_text)
        elif filter_0_op == 'not_contains':
            base_queryset = base_queryset.exclude(switch_name_1__icontains=filter_0_text)
        elif filter_0_op == 'equals':
            base_queryset = base_queryset.filter(switch_name_1=filter_0_text)
        elif filter_0_op == 'not_equals':
            base_queryset = base_queryset.exclude(switch_name_1=filter_0_text)
        elif filter_0_op == 'starts':
            base_queryset = base_queryset.filter(switch_name_1__istartswith=filter_0_text)
        elif filter_0_op == 'ends':
            base_queryset = base_queryset.filter(switch_name_1__iendswith=filter_0_text)
    
    if filter_1_text:  # Switch #2 필터
        if filter_1_op == 'contains':
            base_queryset = base_queryset.filter(switch_name_2__icontains=filter_1_text)
        elif filter_1_op == 'not_contains':
            base_queryset = base_queryset.exclude(switch_name_2__icontains=filter_1_text)
        elif filter_1_op == 'equals':
            base_queryset = base_queryset.filter(switch_name_2=filter_1_text)
        elif filter_1_op == 'not_equals':
            base_queryset = base_queryset.exclude(switch_name_2=filter_1_text)
        elif filter_1_op == 'starts':
            base_queryset = base_queryset.filter(switch_name_2__istartswith=filter_1_text)
        elif filter_1_op == 'ends':
            base_queryset = base_queryset.filter(switch_name_2__iendswith=filter_1_text)
    
    if filter_2_text:  # Switch Type 필터
        if filter_2_op == 'contains':
            base_queryset = base_queryset.filter(switch_type__icontains=filter_2_text)
        elif filter_2_op == 'not_contains':
            base_queryset = base_queryset.exclude(switch_type__icontains=filter_2_text)
        elif filter_2_op == 'equals':
            base_queryset = base_queryset.filter(switch_type=filter_2_text)
        elif filter_2_op == 'not_equals':
            base_queryset = base_queryset.exclude(switch_type=filter_2_text)
        elif filter_2_op == 'starts':
            base_queryset = base_queryset.filter(switch_type__istartswith=filter_2_text)
        elif filter_2_op == 'ends':
            base_queryset = base_queryset.filter(switch_type__iendswith=filter_2_text)
    
    # 전역 검색
    if query:
        switches = base_queryset.filter(
            Q(switch_name_1__icontains=query) |
            Q(switch_name_2__icontains=query) |
            Q(serial_number_1__icontains=query) |
            Q(serial_number_2__icontains=query) |
            Q(switch_model_1__model_name__icontains=query) |
            Q(switch_model_2__model_name__icontains=query)
        )
    else:
        switches = base_queryset
    
    # 정렬 처리
    sort_col = request.GET.get('sort_col')
    sort_order = request.GET.get('sort_order', 'asc')
    
    if sort_col:
        try:
            sort_col = int(sort_col)
            if sort_col == 0:  # Switch #1
                switches = switches.order_by(f"{'-' if sort_order == 'desc' else ''}switch_name_1")
            elif sort_col == 1:  # Switch #2
                switches = switches.order_by(f"{'-' if sort_order == 'desc' else ''}switch_name_2")
            elif sort_col == 2:  # Switch Type
                switches = switches.order_by(f"{'-' if sort_order == 'desc' else ''}switch_type")
            elif sort_col == 3:  # Contract End Date
                switches = switches.order_by(f"{'-' if sort_order == 'desc' else ''}contract_end_date")
            else:
                switches = switches.order_by('-created_at')
        except (ValueError, TypeError):
            switches = switches.order_by('-created_at')
    else:
        switches = switches.order_by('-created_at')
    
    # 각 스위치에 연결된 스토리지 수 계산
    switches = switches.annotate(
        connected_storage_count=Count(
            'cluster_storages',
            filter=Q(cluster_storages__is_switch_connected=True, cluster_storages__deleted_at__isnull=True),
            distinct=True
        ) + Count(
            'fabric_pool_storages',
            filter=Q(fabric_pool_storages__is_fabric_pool_connected=True, fabric_pool_storages__deleted_at__isnull=True),
            distinct=True
        )
    )
    
    # 페이지네이션
    paginator = Paginator(switches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'clusterswitch_list.html', {
        'switches': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'sort_col': sort_col,
        'sort_order': sort_order,
        'filter_0_text': filter_0_text,
        'filter_0_op': filter_0_op,
        'filter_1_text': filter_1_text,
        'filter_1_op': filter_1_op,
        'filter_2_text': filter_2_text,
        'filter_2_op': filter_2_op,
    })

@login_required
def clusterswitch_storages(request, pk):
    """스위치에 연결된 스토리지 목록 조회 (AJAX)"""
    try:
        switch = get_object_or_404(ClusterSwitch, pk=pk)
        
        # Cluster Switch로 연결된 스토리지 (is_switch_connected=True이고 cluster_switch가 해당 스위치인 경우)
        cluster_storages = InstallBase.objects.filter(
            cluster_switch=switch,
            is_switch_connected=True,
            deleted_at__isnull=True
        ).select_related('customer', 'product').values(
            'id', 'cluster_name', 'customer__name', 'product__model_name',
            'serial_number_1', 'serial_number_2', 'node_name_1', 'node_name_2'
        )
        
        # Fabric Pool Switch로 연결된 스토리지 (is_fabric_pool_connected=True이고 fabric_pool_switch가 해당 스위치인 경우)
        fabric_pool_storages = InstallBase.objects.filter(
            fabric_pool_switch=switch,
            is_fabric_pool_connected=True,
            deleted_at__isnull=True
        ).select_related('customer', 'product').values(
            'id', 'cluster_name', 'customer__name', 'product__model_name',
            'serial_number_1', 'serial_number_2', 'node_name_1', 'node_name_2'
        )
        
        # 데이터 포맷팅
        cluster_data = []
        for storage in cluster_storages:
            node_names = []
            if storage.get('node_name_1'):
                node_names.append(storage['node_name_1'])
            if storage.get('node_name_2'):
                node_names.append(storage['node_name_2'])
            node_name_display = ' / '.join(node_names) if node_names else '-'
            
            cluster_data.append({
                'id': storage['id'],
                'cluster_name': storage.get('cluster_name', '-'),
                'customer': storage.get('customer__name', '-'),
                'product': storage.get('product__model_name', '-'),
                'serial_number_1': storage.get('serial_number_1', '-'),
                'serial_number_2': storage.get('serial_number_2', ''),
                'node_name': node_name_display,
            })
        
        fabric_pool_data = []
        for storage in fabric_pool_storages:
            node_names = []
            if storage.get('node_name_1'):
                node_names.append(storage['node_name_1'])
            if storage.get('node_name_2'):
                node_names.append(storage['node_name_2'])
            node_name_display = ' / '.join(node_names) if node_names else '-'
            
            fabric_pool_data.append({
                'id': storage['id'],
                'cluster_name': storage.get('cluster_name', '-'),
                'customer': storage.get('customer__name', '-'),
                'product': storage.get('product__model_name', '-'),
                'serial_number_1': storage.get('serial_number_1', '-'),
                'serial_number_2': storage.get('serial_number_2', ''),
                'node_name': node_name_display,
            })
        
        return JsonResponse({
            'cluster_storages': cluster_data,
            'fabric_pool_storages': fabric_pool_data,
        })
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return JsonResponse({
            'error': str(e),
            'detail': error_detail
        }, status=500)

@login_required
def clusterswitch_deleted_list(request):
    """삭제된 스위치 목록 조회"""
    query = request.GET.get('q', '')
    # 삭제된 스위치만 필터링
    base_queryset = ClusterSwitch.objects.filter(deleted_at__isnull=False)
    
    if query:
        switches = base_queryset.filter(
            Q(switch_name_1__icontains=query) |
            Q(switch_name_2__icontains=query) |
            Q(serial_number_1__icontains=query) |
            Q(serial_number_2__icontains=query) |
            Q(switch_model_1__model_name__icontains=query) |
            Q(switch_model_2__model_name__icontains=query)
        ).order_by('-deleted_at')
    else:
        switches = base_queryset.order_by('-deleted_at')
    
    return render(request, 'clusterswitch_deleted_list.html', {
        'switches': switches,
        'query': query
    })

@login_required
def clusterswitch_restore(request, pk):
    """스위치 삭제 취소 처리 (복구)"""
    switch = get_object_or_404(ClusterSwitch, pk=pk)
    
    if request.method == "POST":
        # 삭제 취소: deleted_at 필드를 None으로 설정
        switch.deleted_at = None
        switch.save()
        return redirect('clusterswitch_list')
    
    # GET 요청의 경우 리스트 페이지로 리다이렉트
    return redirect('clusterswitch_list')

@login_required
def clusterswitch_create(request):
    """클러스터 스위치 신규 등록"""
    if request.method == "POST":
        form = ClusterSwitchForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('clusterswitch_list')
    else:
        form = ClusterSwitchForm()
    
    return render(request, 'clusterswitch_form.html', {
        'form': form,
        'title': '신규 클러스터 스위치 등록'
    })

@login_required
def clusterswitch_update(request, pk):
    """클러스터 스위치 수정"""
    switch = get_object_or_404(ClusterSwitch, pk=pk)
    
    if request.method == "POST":
        form = ClusterSwitchForm(request.POST, instance=switch)
        if form.is_valid():
            form.save()
            return redirect('clusterswitch_list')
    else:
        form = ClusterSwitchForm(instance=switch)
    
    return render(request, 'clusterswitch_update.html', {
        'form': form,
        'switch': switch,
        'title': '클러스터 스위치 수정'
    })

@login_required
def clusterswitch_delete(request, pk):
    """클러스터 스위치 삭제 (soft delete)"""
    switch = get_object_or_404(ClusterSwitch, pk=pk)
    if request.method == "POST":
        switch.deleted_at = timezone.now()
        switch.save()
    return redirect('clusterswitch_list')

# SwitchModel 관련 AJAX 뷰
@login_required
def add_switch_model_ajax(request):
    """스위치 모델 AJAX 추가"""
    if request.method == "POST":
        try:
            model_name = request.POST.get('model_name')
            front_image = request.FILES.get('front_image')
            back_image = request.FILES.get('back_image')
            if model_name:
                switch_model = SwitchModel.objects.create(
                    model_name=model_name,
                    front_image=front_image,
                    back_image=back_image
                )
                return JsonResponse({'id': switch_model.id, 'name': switch_model.model_name})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Issue 관련 뷰
@login_required
def issue_list(request):
    """이슈 목록"""
    query = request.GET.get('q', '')
    base_queryset = Issue.objects.filter(deleted_at__isnull=True).select_related(
        'target_cluster', 'target_cluster__customer', 'target_node', 'assigned_engineer'
    )
    
    # 필터 처리
    filter_0_text = request.GET.get('filter_0_text', '')
    filter_0_op = request.GET.get('filter_0_op', 'contains')
    filter_1_text = request.GET.get('filter_1_text', '')
    filter_1_op = request.GET.get('filter_1_op', 'contains')
    filter_2_text = request.GET.get('filter_2_text', '')
    filter_2_op = request.GET.get('filter_2_op', 'contains')
    filter_3_text = request.GET.get('filter_3_text', '')
    filter_3_op = request.GET.get('filter_3_op', 'contains')
    
    if filter_0_text:  # 고객사 필터
        if filter_0_op == 'contains':
            base_queryset = base_queryset.filter(target_cluster__customer__name__icontains=filter_0_text)
        elif filter_0_op == 'not_contains':
            base_queryset = base_queryset.exclude(target_cluster__customer__name__icontains=filter_0_text)
        elif filter_0_op == 'equals':
            base_queryset = base_queryset.filter(target_cluster__customer__name=filter_0_text)
        elif filter_0_op == 'not_equals':
            base_queryset = base_queryset.exclude(target_cluster__customer__name=filter_0_text)
        elif filter_0_op == 'starts':
            base_queryset = base_queryset.filter(target_cluster__customer__name__istartswith=filter_0_text)
        elif filter_0_op == 'ends':
            base_queryset = base_queryset.filter(target_cluster__customer__name__iendswith=filter_0_text)
    
    if filter_1_text:  # 대상 클러스터 필터
        if filter_1_op == 'contains':
            base_queryset = base_queryset.filter(target_cluster__cluster_name__icontains=filter_1_text)
        elif filter_1_op == 'not_contains':
            base_queryset = base_queryset.exclude(target_cluster__cluster_name__icontains=filter_1_text)
        elif filter_1_op == 'equals':
            base_queryset = base_queryset.filter(target_cluster__cluster_name=filter_1_text)
        elif filter_1_op == 'not_equals':
            base_queryset = base_queryset.exclude(target_cluster__cluster_name=filter_1_text)
        elif filter_1_op == 'starts':
            base_queryset = base_queryset.filter(target_cluster__cluster_name__istartswith=filter_1_text)
        elif filter_1_op == 'ends':
            base_queryset = base_queryset.filter(target_cluster__cluster_name__iendswith=filter_1_text)
    
    if filter_2_text:  # 이슈 타입 필터
        if filter_2_op == 'contains':
            base_queryset = base_queryset.filter(issue_type__icontains=filter_2_text)
        elif filter_2_op == 'not_contains':
            base_queryset = base_queryset.exclude(issue_type__icontains=filter_2_text)
        elif filter_2_op == 'equals':
            base_queryset = base_queryset.filter(issue_type=filter_2_text)
        elif filter_2_op == 'not_equals':
            base_queryset = base_queryset.exclude(issue_type=filter_2_text)
        elif filter_2_op == 'starts':
            base_queryset = base_queryset.filter(issue_type__istartswith=filter_2_text)
        elif filter_2_op == 'ends':
            base_queryset = base_queryset.filter(issue_type__iendswith=filter_2_text)
    
    if filter_3_text:  # 상태 필터
        if filter_3_op == 'contains':
            base_queryset = base_queryset.filter(status__icontains=filter_3_text)
        elif filter_3_op == 'not_contains':
            base_queryset = base_queryset.exclude(status__icontains=filter_3_text)
        elif filter_3_op == 'equals':
            base_queryset = base_queryset.filter(status=filter_3_text)
        elif filter_3_op == 'not_equals':
            base_queryset = base_queryset.exclude(status=filter_3_text)
        elif filter_3_op == 'starts':
            base_queryset = base_queryset.filter(status__istartswith=filter_3_text)
        elif filter_3_op == 'ends':
            base_queryset = base_queryset.filter(status__iendswith=filter_3_text)
    
    # 전역 검색
    if query:
        issues = base_queryset.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(case_number__icontains=query) |
            Q(target_cluster__cluster_name__icontains=query) |
            Q(target_node__cluster_name__icontains=query) |
            Q(status__icontains=query)
        )
    else:
        issues = base_queryset
    
    # 정렬 처리
    sort_col = request.GET.get('sort_col')
    sort_order = request.GET.get('sort_order', 'asc')
    
    if sort_col:
        try:
            sort_col = int(sort_col)
            if sort_col == 0:  # 고객사
                issues = issues.order_by(f"{'-' if sort_order == 'desc' else ''}target_cluster__customer__name")
            elif sort_col == 1:  # 대상 클러스터
                issues = issues.order_by(f"{'-' if sort_order == 'desc' else ''}target_cluster__cluster_name")
            elif sort_col == 2:  # 이슈 타입/상태
                issues = issues.order_by(f"{'-' if sort_order == 'desc' else ''}issue_type", f"{'-' if sort_order == 'desc' else ''}status")
            elif sort_col == 3:  # 케이스 번호
                issues = issues.order_by(f"{'-' if sort_order == 'desc' else ''}case_number")
            elif sort_col == 4:  # 이슈 제목
                issues = issues.order_by(f"{'-' if sort_order == 'desc' else ''}title")
            elif sort_col == 5:  # 이슈 일자
                issues = issues.order_by(f"{'-' if sort_order == 'desc' else ''}issue_date")
            else:
                issues = issues.order_by('-issue_date')
        except (ValueError, TypeError):
            issues = issues.order_by('-issue_date')
        # 정렬이 지정된 경우에도 미완료 건을 먼저 표시
        # 하지만 최근 발생일자 순을 유지하기 위해 issue_date 기준으로 추가 정렬
        issues = issues.order_by('-issue_date')
        issues_list = list(issues)
        incomplete = []
        complete = []
        for issue in issues_list:
            if issue.status != '종료':
                incomplete.append(issue)
            else:
                complete.append(issue)
        # 각 그룹 내에서 최근 발생일자 순 유지 (이미 정렬되어 있음)
        issues_list = incomplete + complete
        # QuerySet으로 다시 변환할 수 없으므로 리스트로 처리
        from django.core.paginator import Paginator as ListPaginator
        paginator = ListPaginator(issues_list, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    else:
        # 기본 정렬: 완료되지 않은 케이스(status != '종료')를 먼저, 그 다음 완료된 케이스
        # 최근 발생일자 순으로 정렬 (내림차순)
        issues = issues.order_by('-issue_date')
        issues_list = list(issues)
        incomplete = []
        complete = []
        for issue in issues_list:
            if issue.status != '종료':
                incomplete.append(issue)
            else:
                complete.append(issue)
        # 최근 발생일자 순으로 정렬 (이미 issue_date 내림차순으로 정렬되어 있음)
        # 완료/미완료 구분선 추가
        if incomplete and complete:
            incomplete[-1].show_divider = True
        issues_list = incomplete + complete
        # QuerySet으로 다시 변환할 수 없으므로 리스트로 처리
        from django.core.paginator import Paginator as ListPaginator
        paginator = ListPaginator(issues_list, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    
    return render(request, 'issue_list.html', {
        'issues': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'sort_col': sort_col,
        'sort_order': sort_order,
        'filter_0_text': filter_0_text,
        'filter_0_op': filter_0_op,
        'filter_1_text': filter_1_text,
        'filter_1_op': filter_1_op,
        'filter_2_text': filter_2_text,
        'filter_2_op': filter_2_op,
        'filter_3_text': filter_3_text,
        'filter_3_op': filter_3_op,
    })

@login_required
def issue_deleted_list(request):
    """삭제된 이슈 목록"""
    query = request.GET.get('q', '')
    base_queryset = Issue.objects.filter(deleted_at__isnull=False)
    
    if query:
        issues = base_queryset.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(case_number__icontains=query) |
            Q(target_cluster__cluster_name__icontains=query) |
            Q(target_node__cluster_name__icontains=query)
        ).order_by('-deleted_at')
    else:
        issues = base_queryset.order_by('-deleted_at')
    
    return render(request, 'issue_deleted_list.html', {
        'issues': issues,
        'query': query
    })

@login_required
def issue_create(request):
    """이슈 신규 등록"""
    target_node_id = request.GET.get('target_node', None)
    
    if request.method == "POST":
        form = IssueForm(request.POST, target_node_id=target_node_id)
        if form.is_valid():
            obj = form.save(commit=False)
            # target_node_number 저장
            target_node_number = request.POST.get('target_node_number', '').strip()
            if target_node_number:
                try:
                    obj.target_node_number = int(target_node_number)
                except (ValueError, TypeError):
                    # target_node가 있으면 기본값 설정
                    if obj.target_node:
                        # node_name_1이 있으면 1, node_name_2만 있으면 2
                        if obj.target_node.node_name_1:
                            obj.target_node_number = 1
                        elif obj.target_node.node_name_2:
                            obj.target_node_number = 2
            elif obj.target_node:
                # target_node_number가 없지만 target_node가 있으면 기본값 설정
                if obj.target_node.node_name_1:
                    obj.target_node_number = 1
                elif obj.target_node.node_name_2:
                    obj.target_node_number = 2
            obj.save()
            return redirect('issue_list')
    else:
        form = IssueForm(target_node_id=target_node_id)
        # 엔지니어 이름을 성+이름으로 표시하도록 수정 (활성화된 유저만)
        User = get_user_model()
        form.fields['assigned_engineer'].choices = [
            (u.id, f"{u.last_name}{u.first_name}") for u in User.objects.filter(is_active=True)
        ]
    
    return render(request, 'issue_form.html', {
        'form': form,
        'title': '신규 이슈 등록'
    })

@login_required
def issue_detail(request, pk):
    """이슈 상세"""
    issue = get_object_or_404(Issue, pk=pk)
    rmas = RMA.objects.filter(case_number=issue, deleted_at__isnull=True).order_by('-created_at')
    
    return render(request, 'issue_detail.html', {
        'issue': issue,
        'rmas': rmas
    })

@login_required
def issue_update(request, pk):
    """이슈 수정"""
    issue = get_object_or_404(Issue, pk=pk)
    
    if request.method == "POST":
        form = IssueForm(request.POST, instance=issue)
        if form.is_valid():
            obj = form.save(commit=False)
            # target_cluster와 target_node는 hidden input으로 전달됨
            target_cluster_id = request.POST.get('target_cluster')
            if target_cluster_id:
                try:
                    obj.target_cluster = InstallBase.objects.get(pk=target_cluster_id)
                except InstallBase.DoesNotExist:
                    obj.target_cluster = issue.target_cluster
            else:
                obj.target_cluster = issue.target_cluster
            
            target_node_id = request.POST.get('target_node')
            target_node_number = request.POST.get('target_node_number', '').strip()
            if target_node_id:
                try:
                    obj.target_node = InstallBase.objects.get(pk=target_node_id)
                    if target_node_number:
                        try:
                            obj.target_node_number = int(target_node_number)
                        except (ValueError, TypeError):
                            # 기본값 설정
                            if obj.target_node.node_name_1:
                                obj.target_node_number = 1
                            elif obj.target_node.node_name_2:
                                obj.target_node_number = 2
                            else:
                                obj.target_node_number = issue.target_node_number
                    else:
                        # target_node_number가 없으면 기본값 설정
                        if obj.target_node.node_name_1:
                            obj.target_node_number = 1
                        elif obj.target_node.node_name_2:
                            obj.target_node_number = 2
                        else:
                            obj.target_node_number = issue.target_node_number
                except InstallBase.DoesNotExist:
                    obj.target_node = issue.target_node
                    obj.target_node_number = issue.target_node_number
            else:
                obj.target_node = issue.target_node
                obj.target_node_number = issue.target_node_number
            obj.save()
            return redirect('issue_detail', pk=pk)
    else:
        form = IssueForm(instance=issue)
        # 엔지니어 이름을 성+이름으로 표시하도록 수정 (활성화된 유저만)
        User = get_user_model()
        form.fields['assigned_engineer'].choices = [
            (u.id, f"{u.last_name}{u.first_name}") for u in User.objects.filter(is_active=True)
        ]
    
    return render(request, 'issue_update.html', {
        'form': form,
        'issue': issue,
        'title': '이슈 수정'
    })

@login_required
def issue_delete(request, pk):
    """이슈 삭제 (soft delete)"""
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == "POST":
        issue.deleted_at = timezone.now()
        issue.save()
    return redirect('issue_list')

@login_required
def issue_restore(request, pk):
    """이슈 삭제 취소"""
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == "POST":
        issue.deleted_at = None
        issue.save()
    return redirect('issue_list')

@login_required
def issue_complete(request, pk):
    """이슈 완료 처리"""
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == "POST":
        end_date = request.POST.get('end_date')
        if end_date:
            issue.end_date = end_date
            issue.status = 'closed'
        issue.save()
        return redirect('issue_list')

# RMA 관련 뷰
@login_required
def rma_list(request):
    """RMA 목록"""
    query = request.GET.get('q', '')
    base_queryset = RMA.objects.filter(deleted_at__isnull=True).select_related(
        'case_number', 'case_number__target_cluster', 'case_number__target_cluster__customer',
        'case_number__target_node', 'part'
    )
    
    # 필터 처리
    filter_0_text = request.GET.get('filter_0_text', '')
    filter_0_op = request.GET.get('filter_0_op', 'contains')
    filter_1_text = request.GET.get('filter_1_text', '')
    filter_1_op = request.GET.get('filter_1_op', 'contains')
    filter_2_text = request.GET.get('filter_2_text', '')
    filter_2_op = request.GET.get('filter_2_op', 'contains')
    filter_3_text = request.GET.get('filter_3_text', '')
    filter_3_op = request.GET.get('filter_3_op', 'contains')
    
    if filter_0_text:  # 고객사 필터
        if filter_0_op == 'contains':
            base_queryset = base_queryset.filter(case_number__target_cluster__customer__name__icontains=filter_0_text)
        elif filter_0_op == 'not_contains':
            base_queryset = base_queryset.exclude(case_number__target_cluster__customer__name__icontains=filter_0_text)
        elif filter_0_op == 'equals':
            base_queryset = base_queryset.filter(case_number__target_cluster__customer__name=filter_0_text)
        elif filter_0_op == 'not_equals':
            base_queryset = base_queryset.exclude(case_number__target_cluster__customer__name=filter_0_text)
        elif filter_0_op == 'starts':
            base_queryset = base_queryset.filter(case_number__target_cluster__customer__name__istartswith=filter_0_text)
        elif filter_0_op == 'ends':
            base_queryset = base_queryset.filter(case_number__target_cluster__customer__name__iendswith=filter_0_text)
    
    if filter_1_text:  # 케이스 번호 필터
        if filter_1_op == 'contains':
            base_queryset = base_queryset.filter(case_number__case_number__icontains=filter_1_text)
        elif filter_1_op == 'not_contains':
            base_queryset = base_queryset.exclude(case_number__case_number__icontains=filter_1_text)
        elif filter_1_op == 'equals':
            base_queryset = base_queryset.filter(case_number__case_number=filter_1_text)
        elif filter_1_op == 'not_equals':
            base_queryset = base_queryset.exclude(case_number__case_number=filter_1_text)
        elif filter_1_op == 'starts':
            base_queryset = base_queryset.filter(case_number__case_number__istartswith=filter_1_text)
        elif filter_1_op == 'ends':
            base_queryset = base_queryset.filter(case_number__case_number__iendswith=filter_1_text)
    
    if filter_2_text:  # RMA 번호 필터
        if filter_2_op == 'contains':
            base_queryset = base_queryset.filter(rma_number__icontains=filter_2_text)
        elif filter_2_op == 'not_contains':
            base_queryset = base_queryset.exclude(rma_number__icontains=filter_2_text)
        elif filter_2_op == 'equals':
            base_queryset = base_queryset.filter(rma_number=filter_2_text)
        elif filter_2_op == 'not_equals':
            base_queryset = base_queryset.exclude(rma_number=filter_2_text)
        elif filter_2_op == 'starts':
            base_queryset = base_queryset.filter(rma_number__istartswith=filter_2_text)
        elif filter_2_op == 'ends':
            base_queryset = base_queryset.filter(rma_number__iendswith=filter_2_text)
    
    if filter_3_text:  # 반납 여부 필터
        if filter_3_op == 'contains':
            base_queryset = base_queryset.filter(return_status__icontains=filter_3_text)
        elif filter_3_op == 'not_contains':
            base_queryset = base_queryset.exclude(return_status__icontains=filter_3_text)
        elif filter_3_op == 'equals':
            base_queryset = base_queryset.filter(return_status=filter_3_text)
        elif filter_3_op == 'not_equals':
            base_queryset = base_queryset.exclude(return_status=filter_3_text)
        elif filter_3_op == 'starts':
            base_queryset = base_queryset.filter(return_status__istartswith=filter_3_text)
        elif filter_3_op == 'ends':
            base_queryset = base_queryset.filter(return_status__iendswith=filter_3_text)
    
    # 전역 검색
    if query:
        rmas = base_queryset.filter(
            Q(rma_number__icontains=query) |
            Q(part__part_number__icontains=query) |
            Q(case_number__case_number__icontains=query) |
            Q(case_number__title__icontains=query)
        )
    else:
        rmas = base_queryset
    
    # 정렬 처리
    sort_col = request.GET.get('sort_col')
    sort_order = request.GET.get('sort_order', 'asc')
    
    if sort_col:
        try:
            sort_col = int(sort_col)
            if sort_col == 0:  # 고객사
                rmas = rmas.order_by(f"{'-' if sort_order == 'desc' else ''}case_number__target_cluster__customer__name")
            elif sort_col == 1:  # 케이스 번호
                rmas = rmas.order_by(f"{'-' if sort_order == 'desc' else ''}case_number__case_number")
            elif sort_col == 2:  # RMA 번호
                rmas = rmas.order_by(f"{'-' if sort_order == 'desc' else ''}rma_number")
            elif sort_col == 3:  # 파트 정보
                rmas = rmas.order_by(f"{'-' if sort_order == 'desc' else ''}part__part_number")
            elif sort_col == 4:  # 반납 / 배송
                rmas = rmas.order_by(f"{'-' if sort_order == 'desc' else ''}return_status", f"{'-' if sort_order == 'desc' else ''}is_delayed", f"{'-' if sort_order == 'desc' else ''}delivery_date")
            else:
                rmas = rmas.order_by('-created_at')
        except (ValueError, TypeError):
            rmas = rmas.order_by('-created_at')
        # 정렬이 지정된 경우에도 미완료 건을 먼저 표시
        # 하지만 최근 일자 순을 유지하기 위해 created_at 기준으로 추가 정렬
        rmas = rmas.order_by('-created_at')
        rmas_list = list(rmas)
        incomplete = []
        complete = []
        for rma in rmas_list:
            if rma.return_status == 'not_returned' or rma.is_delayed == 'not_delivered':
                incomplete.append(rma)
            else:
                complete.append(rma)
        # 각 그룹 내에서 최근 일자 순 유지 (이미 정렬되어 있음)
        rmas_list = incomplete + complete
        # QuerySet으로 다시 변환할 수 없으므로 리스트로 처리
        from django.core.paginator import Paginator as ListPaginator
        paginator = ListPaginator(rmas_list, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    else:
        # 기본 정렬: 완료되지 않은 건(미반납 또는 배송 미완료)을 먼저, 그 다음 완료된 건
        # 최근 일자(created_at) 기준 내림차순 정렬
        rmas = rmas.order_by('-created_at')
        rmas_list = list(rmas)
        incomplete = []
        complete = []
        for rma in rmas_list:
            if rma.return_status == 'not_returned' or rma.is_delayed == 'not_delivered':
                incomplete.append(rma)
            else:
                complete.append(rma)
        # 최근 일자 순으로 정렬 (이미 created_at 내림차순으로 정렬되어 있음)
        # 완료/미완료 구분선 추가
        if incomplete and complete:
            incomplete[-1].show_divider = True
        rmas_list = incomplete + complete
        # QuerySet으로 다시 변환할 수 없으므로 리스트로 처리
        from django.core.paginator import Paginator as ListPaginator
        paginator = ListPaginator(rmas_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'rma_list.html', {
            'rmas': page_obj,
            'page_obj': page_obj,
            'is_paginated': page_obj.has_other_pages(),
            'query': query,
            'sort_col': sort_col,
            'sort_order': sort_order,
            'filter_0_text': filter_0_text,
            'filter_0_op': filter_0_op,
            'filter_1_text': filter_1_text,
            'filter_1_op': filter_1_op,
            'filter_2_text': filter_2_text,
            'filter_2_op': filter_2_op,
            'filter_3_text': filter_3_text,
            'filter_3_op': filter_3_op,
        })
    
    # 페이지네이션
    paginator = Paginator(rmas, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'rma_list.html', {
        'rmas': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'sort_col': sort_col,
        'sort_order': sort_order,
        'filter_0_text': filter_0_text,
        'filter_0_op': filter_0_op,
        'filter_1_text': filter_1_text,
        'filter_1_op': filter_1_op,
        'filter_2_text': filter_2_text,
        'filter_2_op': filter_2_op,
        'filter_3_text': filter_3_text,
        'filter_3_op': filter_3_op,
    })

@login_required
def rma_deleted_list(request):
    """삭제된 RMA 목록"""
    query = request.GET.get('q', '')
    base_queryset = RMA.objects.filter(deleted_at__isnull=False)
    
    if query:
        rmas = base_queryset.filter(
            Q(rma_number__icontains=query) |
            Q(part__part_number__icontains=query) |
            Q(case_number__case_number__icontains=query)
        ).order_by('-deleted_at')
    else:
        rmas = base_queryset.order_by('-deleted_at')
    
    return render(request, 'rma_deleted_list.html', {
        'rmas': rmas,
        'query': query
    })

@login_required
def rma_create(request):
    """RMA 신규 등록 (여러 개 동시 등록 가능)"""
    case_number_id = request.GET.get('case_number', None)
    
    if request.method == "POST":
        rma_quantity = int(request.POST.get('rma_quantity', 1))
        case_number_id_from_form = request.POST.get('case_number')
        if case_number_id_from_form:
            try:
                case = Issue.objects.get(pk=case_number_id_from_form)
            except Issue.DoesNotExist:
                case = None
        else:
            case = None
        
        # RMA 수량만큼 RMA 생성
        created_count = 0
        for i in range(rma_quantity):
            try:
                part_id = request.POST.get(f'part_id_{i}')
                if not part_id:
                    continue
                
                part = Part.objects.get(pk=part_id)
                rma = RMA.objects.create(
                    case_number=case,
                    rma_number=request.POST.get(f'rma_number_{i}', ''),
                    return_required=request.POST.get(f'return_required_{i}', 'required'),
                    part=part,
                    part_quantity=int(request.POST.get(f'part_quantity_{i}', 1)),
                    delivery_region=request.POST.get(f'delivery_region_{i}', ''),
                    delivery_date=request.POST.get(f'delivery_date_{i}') or None,
                    return_region=request.POST.get(f'return_region_{i}', ''),
                    return_date=request.POST.get(f'return_date_{i}') or None,
                    is_delayed=request.POST.get(f'is_delayed_{i}', 'normal'),
                    return_status=request.POST.get(f'return_status_{i}', 'not_returned')
                )
                created_count += 1
            except Exception as e:
                print(f"Error creating RMA {i}: {e}")
                continue
        
        if created_count > 0:
            # 케이스 번호가 있으면 이슈 상세로, 없으면 RMA 리스트로
            if case_number_id or case:
                return redirect('issue_detail', pk=(case_number_id or case.pk))
            return redirect('rma_list')
        else:
            # 에러 처리
            form = RMAForm(case_number_id=case_number_id)
            return render(request, 'rma_form.html', {
                'form': form,
                'title': '신규 RMA 등록',
                'error': 'RMA 등록에 실패했습니다.',
                'case_number_id': case_number_id
            })
    else:
        form = RMAForm(case_number_id=case_number_id)
    
    return render(request, 'rma_form.html', {
        'form': form,
        'title': '신규 RMA 등록',
        'case_number_id': case_number_id
    })

@login_required
def rma_update(request, pk):
    """RMA 수정"""
    rma = get_object_or_404(RMA, pk=pk)
    
    if request.method == "POST":
        form = RMAForm(request.POST, instance=rma)
        if form.is_valid():
            # disabled 필드는 POST에 포함되지 않으므로 원래 값으로 복원
            obj = form.save(commit=False)
            obj.case_number = rma.case_number
            obj.save()
            return redirect('rma_list')
        else:
            # 폼 에러 디버깅
            print("Form errors:", form.errors)
            print("Form non_field_errors:", form.non_field_errors())
    else:
        form = RMAForm(instance=rma)
    
    # 서비스 레벨 정보 가져오기
    service_level = None
    if rma.case_number and rma.case_number.target_cluster:
        service_level = rma.case_number.target_cluster.service_level
    
    return render(request, 'rma_update.html', {
        'form': form,
        'rma': rma,
        'service_level': service_level,
        'part_category': rma.part.category if rma.part else None,
        'title': 'RMA 수정'
    })

@login_required
def rma_delete(request, pk):
    """RMA 삭제 (soft delete)"""
    rma = get_object_or_404(RMA, pk=pk)
    if request.method == "POST":
        rma.deleted_at = timezone.now()
        rma.save()
    return redirect('rma_list')

@login_required
def rma_restore(request, pk):
    """RMA 삭제 취소"""
    rma = get_object_or_404(RMA, pk=pk)
    if request.method == "POST":
        rma.deleted_at = None
        rma.save()
    return redirect('rma_list')

@login_required
def rma_delivery(request, pk):
    """RMA 배송 완료 처리"""
    rma = get_object_or_404(RMA, pk=pk)
    if request.method == "POST":
        delivery_date = request.POST.get('delivery_date')
        is_delayed = request.POST.get('is_delayed', 'normal')
        if delivery_date:
            rma.delivery_date = delivery_date
        rma.is_delayed = is_delayed
        rma.save()
        messages.success(request, '배송 완료 처리되었습니다.')
    else:
        messages.error(request, '배송 일자를 입력해주세요.')
    return redirect('rma_list')

@login_required
def rma_return(request, pk):
    """RMA 반납 처리"""
    rma = get_object_or_404(RMA, pk=pk)
    if request.method == "POST":
        return_region = request.POST.get('return_region')
        return_date = request.POST.get('return_date')
        if return_date:
            rma.return_region = return_region or ''
            rma.return_date = return_date
            rma.return_status = 'returned'
            rma.save()
            messages.success(request, '반납 처리되었습니다.')
        else:
            messages.error(request, '반납 일자를 입력해주세요.')
    return redirect('rma_list')

# Part 관련 AJAX 뷰
@login_required
def add_part_ajax(request):
    """파트 AJAX 추가"""
    if request.method == "POST":
        try:
            part_number = request.POST.get('part_number')
            category = request.POST.get('category')
            part_type = request.POST.get('part_type')
            description = request.POST.get('description', '')
            if part_number and category and part_type:
                part = Part.objects.create(
                    part_number=part_number,
                    category=category,
                    part_type=part_type,
                    description=description
                )
                return JsonResponse({'id': part.id, 'name': part.part_number, 'part_type': part.part_type})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def get_parts_by_category_ajax(request):
    """카테고리별 파트 조회 (AJAX)"""
    category = request.GET.get('category')
    part_type = request.GET.get('part_type', '')
    part_id = request.GET.get('part_id')
    search = request.GET.get('q') or request.GET.get('search', '')  # q 또는 search 파라미터 지원
    
    # part_id가 있으면 해당 파트 정보 반환
    if part_id:
        try:
            part = Part.objects.get(pk=part_id)
            return JsonResponse({
                'part': {
                    'id': part.id,
                    'part_number': part.part_number,
                    'category': part.category,
                    'part_type': part.part_type,
                    'description': part.description
                }
            })
        except Part.DoesNotExist:
            return JsonResponse({'error': 'Part not found'}, status=404)
    
    # 검색어가 있으면 전체 검색
    if search:
        parts = Part.objects.filter(
            Q(part_number__icontains=search) |
            Q(description__icontains=search)
        )
        if category:
            parts = parts.filter(category=category)
        if part_type:
            parts = parts.filter(part_type=part_type)
        parts = parts.order_by('part_number')
        
        data = [{'id': p.id, 'part_number': p.part_number, 'category': p.category, 'part_type': p.part_type, 'description': p.description} for p in parts]
        return JsonResponse({'parts': data})
    
    # 카테고리만 있으면 카테고리별 필터링
    if category:
        parts = Part.objects.filter(category=category)
        if part_type:
            parts = parts.filter(part_type=part_type)
        parts = parts.order_by('part_number')
        
        data = [{'id': p.id, 'part_number': p.part_number, 'category': p.category, 'part_type': p.part_type, 'description': p.description} for p in parts]
        return JsonResponse({'parts': data})
    
    return JsonResponse({'parts': []})

@login_required
def get_cluster_nodes_ajax(request):
    """클러스터/노드 검색 (AJAX)"""
    query = request.GET.get('q', '')
    base_queryset = InstallBase.objects.filter(deleted_at__isnull=True)
    
    if query:
        nodes = base_queryset.filter(
            Q(cluster_name__icontains=query) |
            Q(node_name_1__icontains=query) |
            Q(node_name_2__icontains=query) |
            Q(serial_number_1__icontains=query) |
            Q(serial_number_2__icontains=query)
        ).order_by('cluster_name', 'node_name_1')[:50]
    else:
        nodes = base_queryset.order_by('cluster_name', 'node_name_1')[:50]
    
    data = []
    for node in nodes:
        node_name = ''
        if node.node_name_1:
            node_name = node.node_name_1
        if node.node_name_2:
            node_name += ' / ' + node.node_name_2 if node_name else node.node_name_2
        
        serial_number = node.serial_number_1
        if node.serial_number_2:
            serial_number += ' / ' + node.serial_number_2
        
        data.append({
            'id': node.id,
            'cluster_name': node.cluster_name,
            'node_name': node_name,
            'serial_number': serial_number
        })
    
    return JsonResponse({'nodes': data})

@login_required
def get_clusters_ajax(request):
    """클러스터 목록 조회 (AJAX) - 중복 제거, 페이지네이션"""
    query = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))
    per_page = 20  # 페이지당 항목 수
    
    base_queryset = InstallBase.objects.filter(deleted_at__isnull=True)
    
    if query:
        clusters = base_queryset.filter(
            Q(cluster_name__icontains=query)
        ).values('cluster_name').distinct().order_by('cluster_name')
    else:
        clusters = base_queryset.values('cluster_name').distinct().order_by('cluster_name')
    
    # 페이지네이션
    total_count = clusters.count()
    start = (page - 1) * per_page
    end = start + per_page
    paginated_clusters = clusters[start:end]
    
    data = []
    for cluster_name_dict in paginated_clusters:
        cluster_name = cluster_name_dict['cluster_name']
        # 해당 클러스터의 노드들
        cluster_nodes = base_queryset.filter(cluster_name=cluster_name)
        
        # 시리얼번호 개수 계산 (serial_number_1과 serial_number_2 모두 고려)
        serial_count = 0
        for node in cluster_nodes:
            if node.serial_number_1:
                serial_count += 1
            if node.serial_number_2:
                serial_count += 1
        
        # 첫 번째 노드의 ID를 클러스터 ID로 사용
        first_node = cluster_nodes.first()
        
        data.append({
            'id': first_node.id if first_node else None,
            'cluster_name': cluster_name,
            'serial_count': serial_count
        })
    
    return JsonResponse({
        'clusters': data,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'has_next': end < total_count,
        'has_prev': page > 1
    })

@login_required
def get_customers_ajax(request):
    """고객사 목록 조회 (AJAX)"""
    query = request.GET.get('q', '')
    base_queryset = Customer.objects.all()
    
    if query:
        customers = base_queryset.filter(name__icontains=query).order_by('-name')
    else:
        customers = base_queryset.order_by('-name')
    
    data = []
    for customer in customers:
        data.append({
            'id': customer.id,
            'name': customer.name,
            'logo_url': customer.logo.url if customer.logo else None
        })
    
    return JsonResponse({'customers': data})

@login_required
def get_nodes_by_cluster_ajax(request):
    """특정 클러스터의 노드 목록 조회 (AJAX) - 각 노드를 개별적으로 반환"""
    cluster_id = request.GET.get('cluster_id')
    query = request.GET.get('q', '')
    
    if not cluster_id:
        return JsonResponse({'nodes': []})
    
    try:
        cluster_node = InstallBase.objects.get(pk=cluster_id, deleted_at__isnull=True)
        cluster_name = cluster_node.cluster_name
        
        base_queryset = InstallBase.objects.filter(
            cluster_name=cluster_name,
            deleted_at__isnull=True
        )
        
        if query:
            nodes = base_queryset.filter(
                Q(node_name_1__icontains=query) |
                Q(node_name_2__icontains=query) |
                Q(serial_number_1__icontains=query) |
                Q(serial_number_2__icontains=query)
            ).order_by('node_name_1')
        else:
            nodes = base_queryset.order_by('node_name_1')
        
        data = []
        for node in nodes:
            # node_name_1이 있으면 별도 노드로 추가
            if node.node_name_1:
                data.append({
                    'id': node.id,
                    'node_name': node.node_name_1,
                    'serial_number': node.serial_number_1 or '',
                    'node_number': 1
                })
            
            # node_name_2가 있으면 별도 노드로 추가
            if node.node_name_2:
                data.append({
                    'id': node.id,
                    'node_name': node.node_name_2,
                    'serial_number': node.serial_number_2 or '',
                    'node_number': 2
                })
        
        return JsonResponse({'nodes': data})
    except InstallBase.DoesNotExist:
        return JsonResponse({'nodes': []})

@login_required
def get_node_info_ajax(request):
    """노드 정보 조회 (AJAX)"""
    node_id = request.GET.get('node_id')
    
    if not node_id:
        return JsonResponse({'node': None})
    
    try:
        node = InstallBase.objects.get(pk=node_id, deleted_at__isnull=True)
        
        node_number = request.GET.get('node_number')  # 1 또는 2
        
        # node_number가 지정되면 해당 노드만 반환
        if node_number == '1' and node.node_name_1:
            node_name = node.node_name_1
        elif node_number == '2' and node.node_name_2:
            node_name = node.node_name_2
        else:
            # node_number가 없으면 기존 로직 (둘 다 표시)
            node_name = ''
            if node.node_name_1:
                node_name = node.node_name_1
            if node.node_name_2:
                node_name += ' / ' + node.node_name_2 if node_name else node.node_name_2
        
        # 클러스터의 첫 번째 노드 ID 찾기
        cluster_first_node = InstallBase.objects.filter(
            cluster_name=node.cluster_name,
            deleted_at__isnull=True
        ).order_by('id').first()
        
        return JsonResponse({
            'node': {
                'id': node.id,
                'cluster_id': cluster_first_node.id if cluster_first_node else node.id,
                'cluster_name': node.cluster_name,
                'node_name': node_name,
                'node_name_1': node.node_name_1 or '',
                'node_name_2': node.node_name_2 or '',
                'serial_number_1': node.serial_number_1 or '',
                'serial_number_2': node.serial_number_2 or ''
            }
        })
    except InstallBase.DoesNotExist:
        return JsonResponse({'node': None})

@login_required
def get_cases_ajax(request):
    """케이스 번호 검색 (AJAX) - 진행중인 케이스만, 페이지네이션"""
    query = request.GET.get('q', '').strip()
    case_number_param = request.GET.get('case_number', None)
    page = int(request.GET.get('page', 1))
    per_page = 20  # 페이지당 항목 수
    
    # 진행중인 케이스만 필터링 (closed가 아닌 것들)
    base_queryset = Issue.objects.filter(deleted_at__isnull=True).exclude(status='closed').select_related(
        'target_cluster', 'target_node'
    )
    
    if case_number_param:
        # case_number 파라미터가 숫자면 ID로, 아니면 케이스 번호로 검색
        try:
            case_id = int(case_number_param)
            cases = base_queryset.filter(id=case_id)
        except (ValueError, TypeError):
            cases = base_queryset.filter(case_number__icontains=case_number_param)
    elif query:
        cases = base_queryset.filter(
            Q(case_number__icontains=query) |
            Q(title__icontains=query) |
            Q(target_cluster__cluster_name__icontains=query)
        ).order_by('-issue_date')
    else:
        cases = base_queryset.order_by('-issue_date')
    
    # 페이지네이션
    total_count = cases.count()
    start = (page - 1) * per_page
    end = start + per_page
    paginated_cases = cases[start:end]
    
    data = []
    for case in paginated_cases:
        # status_display 가져오기
        status_display = ''
        if case.status:
            status_display = case.get_status_display()
        
        # target_cluster 혹은 target_node에서 service_level 가져오기
        ib_info = case.target_cluster or case.target_node
        service_level = "Normal"
        if ib_info and ib_info.service_level:
            service_level = ib_info.service_level
        
        data.append({
            'id': case.id,
            'case_number': case.case_number or f'ISSUE-{case.id}',
            'title': case.title or '',
            'cluster_name': case.target_cluster.cluster_name if case.target_cluster else '-',
            'issue_date': case.issue_date.strftime('%Y-%m-%d') if case.issue_date else '',
            'status_display': status_display,
            'service_level': service_level,
        })
    
    return JsonResponse({
        'cases': data,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'has_next': end < total_count,
        'has_prev': page > 1
    })


def get_issues_api(request):
    query = request.GET.get('q', '')
    issue_id = request.GET.get('id', None)
    case_number_param = request.GET.get('case_number', None)

    issues = Issue.objects.filter(deleted_at__isnull=True)

    if issue_id:
        try:
            issues = issues.filter(id=int(issue_id))
        except (ValueError, TypeError):
            issues = issues.none()
    elif case_number_param:
        # case_number 파라미터가 숫자면 ID로, 아니면 케이스 번호로 검색
        try:
            case_id = int(case_number_param)
            issues = issues.filter(id=case_id)
        except (ValueError, TypeError):
            issues = issues.filter(case_number__icontains=case_number_param)
    elif query:
        issues = issues.filter(case_number__icontains=query) | issues.filter(title__icontains=query)

    data = []
    for i in issues:
        # status_display 가져오기 - status 필드가 있으면 get_status_display() 호출
        status_display = ''
        if i.status:
            status_display = i.get_status_display()
        
        # target_cluster 혹은 target_node에서 service_level 가져오기
        ib_info = i.target_cluster or i.target_node
        sl = "Normal"
        if ib_info and ib_info.service_level:
            sl = ib_info.service_level

        data.append({
            'id': i.id,
            'case_number': i.case_number or '',
            'title': i.title or '',
            'status_display': status_display,  # '진행중' 등 출력
            'service_level': sl,  # '4HR_NRD' 등 출력
        })

    return JsonResponse({'cases': data})
# 엑셀 Export 기능
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from datetime import datetime
from .models import InstallBase, ClusterSwitch, Issue, RMA

@login_required
def export_installbase_excel(request):
    """InstallBase 엑셀 Export"""
    # 삭제되지 않은 장비만 필터링
    queryset = InstallBase.objects.filter(deleted_at__isnull=True).select_related(
        'customer', 'product', 'cluster_switch', 'fabric_pool_switch'
    ).prefetch_related('assigned_engineers').order_by('cluster_name', 'install_date')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "InstallBase"
    
    # 헤더 스타일
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    # 헤더 작성
    headers = [
        '고객사', '클러스터명', '노드명1', '노드명2', '노드번호1', '노드번호2',
        '시리얼번호1', '시리얼번호2', '모델명', '설치위치', '상면번호', 
        '서비스명', '프로젝트', '설치국가', '설치일', 'ONTOP 버전', 
        '점검종류', '서비스레벨', '라이센스타입', '컨트롤러 슬롯',
        '담당엔지니어', '클러스터 스위치 연동', '클러스터 스위치', 
        'Fabric Pool 연동', 'Fabric Pool 스위치',
        'Cluster Mgmt IP', 'Node1 Mgmt IP', 'Node2 Mgmt IP',
        'Node1 BMC IP', 'Node2 BMC IP', 'Other IPs', 'IP Lists',
        'Shelf 모델', 'Disk 정보', '라이센스 정보',
        '계약종료일', '유지보수시작일', '유지보수종료일'
    ]
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 데이터 작성
    for row_num, item in enumerate(queryset, 2):
        engineers = ', '.join([f"{e.last_name}{e.first_name}" if e.last_name or e.first_name else e.username 
                               for e in item.assigned_engineers.all()])
        
        # 클러스터 스위치 정보
        cluster_switch_name = ''
        if item.cluster_switch:
            switch_names = []
            if item.cluster_switch.switch_name_1:
                switch_names.append(item.cluster_switch.switch_name_1)
            if item.cluster_switch.switch_name_2:
                switch_names.append(item.cluster_switch.switch_name_2)
            cluster_switch_name = ' / '.join(switch_names) if switch_names else ''
        
        # Fabric Pool 스위치 정보
        fabric_pool_switch_name = ''
        if item.fabric_pool_switch:
            switch_names = []
            if item.fabric_pool_switch.switch_name_1:
                switch_names.append(item.fabric_pool_switch.switch_name_1)
            if item.fabric_pool_switch.switch_name_2:
                switch_names.append(item.fabric_pool_switch.switch_name_2)
            fabric_pool_switch_name = ' / '.join(switch_names) if switch_names else ''
        
        ws.cell(row=row_num, column=1).value = item.customer.name if item.customer else ''
        ws.cell(row=row_num, column=2).value = item.cluster_name or ''
        ws.cell(row=row_num, column=3).value = item.node_name_1 or ''
        ws.cell(row=row_num, column=4).value = item.node_name_2 or ''
        ws.cell(row=row_num, column=5).value = item.node_number_1 or ''
        ws.cell(row=row_num, column=6).value = item.node_number_2 or ''
        ws.cell(row=row_num, column=7).value = item.serial_number_1 or ''
        ws.cell(row=row_num, column=8).value = item.serial_number_2 or ''
        ws.cell(row=row_num, column=9).value = item.product.model_name if item.product else ''
        ws.cell(row=row_num, column=10).value = item.location or ''
        ws.cell(row=row_num, column=11).value = item.rack_space or ''
        ws.cell(row=row_num, column=12).value = item.service_name or ''
        ws.cell(row=row_num, column=13).value = item.project or ''
        ws.cell(row=row_num, column=14).value = item.get_country_display() if item.country else ''
        ws.cell(row=row_num, column=15).value = item.install_date.strftime('%Y-%m-%d') if item.install_date else ''
        ws.cell(row=row_num, column=16).value = item.ontap_version or ''
        ws.cell(row=row_num, column=17).value = item.get_periodic_inspection_display() if item.periodic_inspection else ''
        ws.cell(row=row_num, column=18).value = item.get_service_level_display() if item.service_level else ''
        ws.cell(row=row_num, column=19).value = item.get_license_type_display() if item.license_type else ''
        ws.cell(row=row_num, column=20).value = item.controller_slots or ''
        ws.cell(row=row_num, column=21).value = engineers
        ws.cell(row=row_num, column=22).value = '예' if item.is_switch_connected else '아니오'
        ws.cell(row=row_num, column=23).value = cluster_switch_name
        ws.cell(row=row_num, column=24).value = '예' if item.is_fabric_pool_connected else '아니오'
        ws.cell(row=row_num, column=25).value = fabric_pool_switch_name
        ws.cell(row=row_num, column=26).value = item.cluster_mgmt_ip or ''
        ws.cell(row=row_num, column=27).value = item.node1_mgmt_ip or ''
        ws.cell(row=row_num, column=28).value = item.node2_mgmt_ip or ''
        ws.cell(row=row_num, column=29).value = item.node1_bmc_ip or ''
        ws.cell(row=row_num, column=30).value = item.node2_bmc_ip or ''
        ws.cell(row=row_num, column=31).value = item.other_ips or ''
        ws.cell(row=row_num, column=32).value = item.ip_lists or ''
        ws.cell(row=row_num, column=33).value = item.shelf_models or ''
        ws.cell(row=row_num, column=34).value = item.disk_info or ''
        ws.cell(row=row_num, column=35).value = item.license_info or ''
        ws.cell(row=row_num, column=36).value = item.contract_end_date.strftime('%Y-%m-%d') if item.contract_end_date else ''
        ws.cell(row=row_num, column=37).value = item.maintenance_start.strftime('%Y-%m-%d') if item.maintenance_start else ''
        ws.cell(row=row_num, column=38).value = item.maintenance_end.strftime('%Y-%m-%d') if item.maintenance_end else ''
    
    # 컬럼 너비 자동 조정
    for col_num in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_num)].width = 15
    
    # 파일명 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'InstallBase_{timestamp}.xlsx'
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
    
    wb.save(response)
    return response

@login_required
def export_switches_excel(request):
    """Switches 엑셀 Export"""
    queryset = ClusterSwitch.objects.filter(deleted_at__isnull=True).select_related(
        'switch_model_1', 'switch_model_2'
    ).order_by('switch_name_1')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Switches"
    
    # 헤더 스타일
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    # 헤더 작성
    headers = [
        '스위치 타입', '스위치명1', '스위치명2', '모델명1', '모델명2',
        '시리얼번호1', '시리얼번호2', 'IP주소1', 'IP주소2',
        '설치일', '유지보수시작일', '유지보수종료일', '계약종료일'
    ]
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 데이터 작성
    for row_num, item in enumerate(queryset, 2):
        ws.cell(row=row_num, column=1).value = item.get_switch_type_display() if item.switch_type else ''
        ws.cell(row=row_num, column=2).value = item.switch_name_1 or ''
        ws.cell(row=row_num, column=3).value = item.switch_name_2 or ''
        ws.cell(row=row_num, column=4).value = item.switch_model_1.model_name if item.switch_model_1 else ''
        ws.cell(row=row_num, column=5).value = item.switch_model_2.model_name if item.switch_model_2 else ''
        ws.cell(row=row_num, column=6).value = item.serial_number_1 or ''
        ws.cell(row=row_num, column=7).value = item.serial_number_2 or ''
        ws.cell(row=row_num, column=8).value = str(item.ip_address_1) if item.ip_address_1 else ''
        ws.cell(row=row_num, column=9).value = str(item.ip_address_2) if item.ip_address_2 else ''
        ws.cell(row=row_num, column=10).value = item.install_date.strftime('%Y-%m-%d') if item.install_date else ''
        ws.cell(row=row_num, column=11).value = item.maintenance_start.strftime('%Y-%m-%d') if item.maintenance_start else ''
        ws.cell(row=row_num, column=12).value = item.maintenance_end.strftime('%Y-%m-%d') if item.maintenance_end else ''
        ws.cell(row=row_num, column=13).value = item.contract_end_date.strftime('%Y-%m-%d') if item.contract_end_date else ''
    
    # 컬럼 너비 자동 조정
    for col_num in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_num)].width = 15
    
    # 파일명 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'Switches_{timestamp}.xlsx'
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
    
    wb.save(response)
    return response

@login_required
def export_issues_excel(request):
    """Issues 엑셀 Export"""
    queryset = Issue.objects.filter(deleted_at__isnull=True).select_related(
        'target_cluster', 'target_cluster__customer', 'target_node', 'assigned_engineer'
    ).order_by('-issue_date')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Issues"
    
    # 헤더 스타일
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    # 헤더 작성
    headers = [
        '고객사', '대상 클러스터', '대상 노드1', '대상 노드2', '이슈 타입',
        '이슈 발생일', '진행 상태', '이슈 제목', '이슈 내용', '이슈 종료일',
        '케이스 번호', '이슈 진행자'
    ]
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 데이터 작성
    for row_num, issue in enumerate(queryset, 2):
        ws.cell(row=row_num, column=1).value = issue.target_cluster.customer.name if issue.target_cluster and issue.target_cluster.customer else ''
        ws.cell(row=row_num, column=2).value = issue.target_cluster.cluster_name if issue.target_cluster else ''
        ws.cell(row=row_num, column=3).value = issue.target_node.node_name_1 if issue.target_node else ''
        ws.cell(row=row_num, column=4).value = issue.target_node.node_name_2 if issue.target_node else ''
        ws.cell(row=row_num, column=5).value = issue.get_issue_type_display() if issue.issue_type else ''
        ws.cell(row=row_num, column=6).value = issue.issue_date.strftime('%Y-%m-%d') if issue.issue_date else ''
        ws.cell(row=row_num, column=7).value = issue.get_status_display() if issue.status else ''
        ws.cell(row=row_num, column=8).value = issue.title or ''
        ws.cell(row=row_num, column=9).value = issue.content or ''
        ws.cell(row=row_num, column=10).value = issue.end_date.strftime('%Y-%m-%d') if issue.end_date else ''
        ws.cell(row=row_num, column=11).value = issue.case_number or ''
        ws.cell(row=row_num, column=12).value = f"{issue.assigned_engineer.last_name}{issue.assigned_engineer.first_name}" if issue.assigned_engineer and (issue.assigned_engineer.last_name or issue.assigned_engineer.first_name) else (issue.assigned_engineer.username if issue.assigned_engineer else '')
    
    # 컬럼 너비 자동 조정
    for col_num in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_num)].width = 15
    
    # 파일명 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'Issues_{timestamp}.xlsx'
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
    
    wb.save(response)
    return response

@login_required
def export_rma_excel(request):
    """RMA 엑셀 Export"""
    queryset = RMA.objects.filter(deleted_at__isnull=True).select_related(
        'case_number', 'case_number__target_cluster', 'case_number__target_cluster__customer',
        'case_number__target_node', 'part'
    ).order_by('-created_at')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "RMA"
    
    # 헤더 스타일
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    # 헤더 작성
    headers = [
        '고객사', '케이스 번호', 'RMA 번호', '파트 넘버', '파트 종류', '파트 타입',
        '파트 수량', '반납 필요 여부', '배송 지역', '배송 일자', '반납 지역',
        '반납 일자', '지연 배송 여부', '반납 여부'
    ]
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 데이터 작성
    for row_num, rma in enumerate(queryset, 2):
        ws.cell(row=row_num, column=1).value = rma.case_number.target_cluster.customer.name if rma.case_number and rma.case_number.target_cluster and rma.case_number.target_cluster.customer else ''
        ws.cell(row=row_num, column=2).value = rma.case_number.case_number if rma.case_number else ''
        ws.cell(row=row_num, column=3).value = rma.rma_number or ''
        ws.cell(row=row_num, column=4).value = rma.part.part_number if rma.part else ''
        ws.cell(row=row_num, column=5).value = rma.part.get_category_display() if rma.part else ''
        ws.cell(row=row_num, column=6).value = rma.part.part_type if rma.part else ''
        ws.cell(row=row_num, column=7).value = rma.part_quantity
        ws.cell(row=row_num, column=8).value = rma.get_return_required_display() if rma.return_required else ''
        ws.cell(row=row_num, column=9).value = rma.delivery_region or ''
        ws.cell(row=row_num, column=10).value = rma.delivery_date.strftime('%Y-%m-%d') if rma.delivery_date else ''
        ws.cell(row=row_num, column=11).value = rma.return_region or ''
        ws.cell(row=row_num, column=12).value = rma.return_date.strftime('%Y-%m-%d') if rma.return_date else ''
        ws.cell(row=row_num, column=13).value = rma.get_is_delayed_display() if rma.is_delayed else ''
        ws.cell(row=row_num, column=14).value = rma.get_return_status_display() if rma.return_status else ''
    
    # 컬럼 너비 자동 조정
    for col_num in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_num)].width = 15
    
    # 파일명 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'RMA_{timestamp}.xlsx'
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
    
    wb.save(response)
    return response

@login_required
@user_passes_test(is_admin, login_url='/')
def netapp_api_management(request):
    """NetApp API 관리 페이지 (관리자만 접근 가능)"""
    config = NetAppAPIConfig.get_config()
    
    if request.method == 'POST':
        if 'update_config' in request.POST:
            config.ntap_uid = request.POST.get('ntap_uid', '')
            config.client_id = request.POST.get('client_id', '')
            config.client_secret = request.POST.get('client_secret', '')
            config.save()
            messages.success(request, 'API 설정이 업데이트되었습니다.')
            return redirect('netapp_api_management')
        
        elif 'test_api' in request.POST:
            try:
                # 최근 성공한 시리얼 번호 찾기 (계약 종료일 정보가 있는 것 우선, 없으면 시리얼 번호만 있는 것)
                recent_serial = InstallBase.objects.filter(
                    deleted_at__isnull=True,
                    contract_end_date__isnull=False
                ).order_by('-updated_at').first()
                
                if not recent_serial:
                    recent_serial = InstallBase.objects.filter(
                        deleted_at__isnull=True,
                        serial_number_1__isnull=False
                    ).exclude(serial_number_1='').order_by('-updated_at').first()

                if not recent_serial:
                    messages.error(request, '테스트할 시리얼 번호를 찾을 수 없습니다. 먼저 시리얼 번호가 있는 장비가 필요합니다.')
                    return redirect('netapp_api_management')
                
                test_serial = recent_serial.serial_number_1
                
                token_url = 'https://api.support.netapp.com/api/token'
                api_url = 'https://api.support.netapp.com/api/support/system-entitlements'
                
                token_response = requests.post(
                    token_url,
                    json={
                        'client_id': config.client_id,
                        'client_secret': config.client_secret
                    },
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                if token_response.status_code != 200:
                    messages.error(request, f'토큰 발급 실패: {token_response.text}')
                    return redirect('netapp_api_management')
                
                token_data = token_response.json()
                token = token_data.get('token') or token_data.get('access_token')
                
                if not token:
                    messages.error(request, '토큰을 받을 수 없습니다.')
                    return redirect('netapp_api_management')
                
                api_response = requests.post(
                    api_url,
                    json={
                        'systemSerialNumber': test_serial,
                        'ntapUID': config.ntap_uid,
                        'fetchSWEntitlement': 'X'
                    },
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/json'
                    },
                    timeout=30
                )
                
                if api_response.status_code != 200:
                    messages.error(request, f'API 호출 실패: {api_response.text}')
                    config.last_test_result = f"실패: {api_response.text}"
                    config.last_test_date = timezone.now()
                    config.save()
                    return redirect('netapp_api_management')
                
                result_data = api_response.json()
                contract_end_str = result_data.get('systemSerialNumberContractEndDate')
                
                if contract_end_str:
                    # 날짜 형식 변환 (DD-MM-YYYY -> YYYY-MM-DD)
                    try:
                        contract_end_date = datetime.strptime(contract_end_str, '%d-%m-%Y').date()
                    except ValueError:
                        try:
                            contract_end_date = datetime.strptime(contract_end_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                contract_end_date = datetime.fromisoformat(contract_end_str.replace('Z', '+00:00')).date()
                            except ValueError:
                                messages.error(request, f'API 응답 날짜 형식 파싱 실패: {contract_end_str}')
                                config.last_test_result = f"실패: 날짜 형식 파싱 오류 - {contract_end_str}"
                                config.last_test_date = timezone.now()
                                config.save()
                                return redirect('netapp_api_management')

                    config.last_test_serial = test_serial
                    config.last_test_date = timezone.now()
                    config.last_test_result = json.dumps(result_data, indent=2, ensure_ascii=False)
                    config.save()
                    messages.success(request, f'API 테스트 성공! 시리얼: {test_serial}, 계약 종료일: {contract_end_date.strftime("%Y-%m-%d")}')
                else:
                    config.last_test_result = json.dumps(result_data, indent=2, ensure_ascii=False)
                    config.last_test_date = timezone.now()
                    config.save()
                    messages.warning(request, f'API 호출은 성공했지만 계약 종료일 정보가 없습니다. 시리얼: {test_serial}')
                
            except Exception as e:
                messages.error(request, f'API 테스트 중 오류 발생: {str(e)}')
                config.last_test_result = f"오류: {str(e)}"
                config.last_test_date = timezone.now()
                config.save()
            
            return redirect('netapp_api_management')
    
    last_test_result_parsed = None
    if config.last_test_result:
        try:
            last_test_result_parsed = json.loads(config.last_test_result)
        except:
            last_test_result_parsed = config.last_test_result
    
    context = {
        'config': config,
        'last_test_result': last_test_result_parsed
    }
    return render(request, 'installbase/netapp_api_management.html', context)


def signup(request):
    """회원 가입"""
    from django.contrib.auth.forms import UserCreationForm
    from django.contrib.auth import login
    
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # 추가 필드 저장
            if 'last_name' in request.POST:
                user.last_name = request.POST['last_name']
            if 'first_name' in request.POST:
                user.first_name = request.POST['first_name']
            if 'email' in request.POST:
                user.email = request.POST['email']
            user.save()
            # 자동 로그인
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'registration/signup.html', {
        'form': form
    })
