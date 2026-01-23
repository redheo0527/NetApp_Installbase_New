from django.db import models
from django.conf import settings
from django.utils import timezone

class Customer(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='고객사명')
    logo = models.ImageField(blank=True, null=True, upload_to='customer_logos/', verbose_name='고객사 로고')

    class Meta:
        verbose_name_plural = "고객사 관리"

    def __str__(self):
        return self.name

class Product(models.Model):
    LINEUP_CHOICES = [
        ('AFF', 'AFF'),
        ('FAS', 'FAS'),
    ]
    lineup = models.CharField(choices=LINEUP_CHOICES, max_length=10, verbose_name='라인업')
    model_name = models.CharField(max_length=100, verbose_name='모델명')
    image = models.ImageField(blank=True, null=True, upload_to='product_images/', verbose_name='모델 이미지')

    class Meta:
        verbose_name_plural = "장비 모델 관리"

    def __str__(self):
        return f"{self.lineup} - {self.model_name}"

class SwitchModel(models.Model):
    model_name = models.CharField(max_length=100, unique=True, verbose_name='스위치 모델명')
    front_image = models.ImageField(blank=True, null=True, upload_to='switch_images/', verbose_name='전면 이미지')
    back_image = models.ImageField(blank=True, null=True, upload_to='switch_images/', verbose_name='후면 이미지')

    class Meta:
        verbose_name_plural = "스위치 모델 관리"

    def __str__(self):
        return self.model_name

class ClusterSwitch(models.Model):
    SWITCH_TYPE_CHOICES = [
        ('cluster', 'Cluster Switch'),
        ('fabric_pool', 'Fabric Pool Switch'),
    ]
    
    switch_type = models.CharField(max_length=20, choices=SWITCH_TYPE_CHOICES, default='cluster', verbose_name='스위치 타입')
    switch_name_1 = models.CharField(max_length=100, null=True, blank=True, verbose_name='스위치 이름 #1')
    switch_name_2 = models.CharField(max_length=100, null=True, blank=True, verbose_name='스위치 이름 #2')
    ip_address_1 = models.GenericIPAddressField(null=True, blank=True, verbose_name='관리 IP #1')
    ip_address_2 = models.GenericIPAddressField(null=True, blank=True, verbose_name='관리 IP #2')
    switch_model_1 = models.ForeignKey(SwitchModel, on_delete=models.PROTECT, related_name='switches_1', null=True, blank=True, verbose_name='스위치 모델 #1')
    switch_model_2 = models.ForeignKey(SwitchModel, on_delete=models.PROTECT, related_name='switches_2', null=True, blank=True, verbose_name='스위치 모델 #2')
    serial_number_1 = models.CharField(max_length=100, null=True, blank=True, verbose_name='시리얼 번호 #1')
    serial_number_2 = models.CharField(max_length=100, null=True, blank=True, verbose_name='시리얼 번호 #2')
    install_date = models.DateField(null=True, blank=True, verbose_name='설치일')
    maintenance_start = models.DateField(null=True, blank=True, verbose_name='유지보수 시작일')
    maintenance_end = models.DateField(null=True, blank=True, verbose_name='유지보수 종료일')
    contract_end_date = models.DateField(null=True, blank=True, verbose_name='백계약 종료일')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='삭제일시')

    class Meta:
        verbose_name_plural = "클러스터 스위치 관리"

    def __str__(self):
        return f"{self.switch_name_1 or ''} / {self.switch_name_2 or ''}"

class InstallBase(models.Model):
    PERIODIC_CHOICES = [
        ('none', '정기점검 비대상'),
        ('monthly', '월 점검'),
        ('quarter', '분기 점검'),
        ('half', '반기 점검'),
    ]
    
    SERVICE_LEVELS = [
        ('4HR_NRD', '4HR_NRD'),
        ('4HR', '4HR'),
        ('Next Business Day', 'Next Business Day'),
        ('no_Contract', '미계약'),
    ]
    
    COUNTRY_CHOICES = [
        ('KR', 'South Korea'),
        ('US', 'United States'),
        ('CN', 'China'),
        ('DE', 'Germany'),
        ('SK', 'Slovakia'),
        ('IN', 'India'),
        ('SG', 'Singapore'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='storages', verbose_name='고객사')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='모델명')
    location = models.CharField(max_length=200, verbose_name='설치 위치')
    rack_space = models.CharField(max_length=100, blank=True, verbose_name='상면 번호')
    service_name = models.CharField(max_length=100, verbose_name='서비스명')
    project = models.CharField(max_length=255, verbose_name='프로젝트명')
    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES, default='KR', verbose_name='설치 국가')
    
    is_switch_connected = models.BooleanField(default=False, verbose_name='클러스터 스위치 연동 여부')
    cluster_switch = models.ForeignKey(ClusterSwitch, on_delete=models.SET_NULL, null=True, blank=True, related_name='cluster_storages', verbose_name='클러스터 스위치', limit_choices_to={'switch_type': 'cluster', 'deleted_at__isnull': True})
    
    is_fabric_pool_connected = models.BooleanField(default=False, verbose_name='Fabric Pool 연동 여부')
    fabric_pool_switch = models.ForeignKey(ClusterSwitch, on_delete=models.SET_NULL, null=True, blank=True, related_name='fabric_pool_storages', verbose_name='Fabric Pool 스위치', limit_choices_to={'switch_type': 'fabric_pool', 'deleted_at__isnull': True})
    assigned_engineers = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='담당 엔지니어')

    serial_number_1 = models.CharField(max_length=100, verbose_name='시리얼 번호(Node 1)')
    serial_number_2 = models.CharField(max_length=100, null=True, blank=True, verbose_name='시리얼 번호(Node 2)')
    node_name_1 = models.CharField(max_length=100, null=True, blank=True, verbose_name='노드1 이름(Node 1)')
    node_name_2 = models.CharField(max_length=100, null=True, blank=True, verbose_name='노드2 이름(Node 2)')
    node_number_1 = models.IntegerField(null=True, blank=True, verbose_name='클러스터 내 노드 번호(Node 1)', help_text='1-40')
    node_number_2 = models.IntegerField(null=True, blank=True, verbose_name='클러스터 내 노드 번호(Node 2)', help_text='1-40')
    cluster_name = models.CharField(max_length=100, verbose_name='Cluster Name')
    ontap_version = models.CharField(max_length=50, verbose_name='ONTAP Version')
    
    periodic_inspection = models.CharField(max_length=20, choices=PERIODIC_CHOICES, default='none', verbose_name='정기점검 주기')
    license_type = models.CharField(max_length=10, choices=[('base', 'Base'), ('one', 'ONTAP ONE')], default='base', verbose_name='라이선스 타입')
    controller_slots = models.TextField(null=True, blank=True, verbose_name='컨트롤러 슬롯')

    install_date = models.DateField(verbose_name='설치일')
    contract_end_date = models.DateField(null=True, blank=True, verbose_name='백계약 종료일')
    maintenance_start = models.DateField(verbose_name='유지보수 시작일')
    maintenance_end = models.DateField(null=True, blank=True, verbose_name='유지보수 종료일')
    service_level = models.CharField(max_length=20, choices=SERVICE_LEVELS, verbose_name='서비스 레벨')
    
    license_info = models.TextField(blank=True, verbose_name='라이센스 정보')
    ip_lists = models.TextField(blank=True, verbose_name='IP Lists (관리/데이터)')
    shelf_models = models.CharField(max_length=200, blank=True, verbose_name='Shelf 모델명')
    disk_info = models.TextField(blank=True, verbose_name='Disk/Shelf 정보 (타입 및 개수)')
    
    cluster_mgmt_ip = models.CharField(max_length=200, null=True, blank=True, verbose_name='Cluster Management IP')
    node1_mgmt_ip = models.CharField(max_length=200, null=True, blank=True, verbose_name='첫번째 노드 Management IP')
    node2_mgmt_ip = models.CharField(max_length=200, null=True, blank=True, verbose_name='두번째 노드 Management IP')
    node1_bmc_ip = models.CharField(max_length=200, null=True, blank=True, verbose_name='첫번째 노드 BMC IP')
    node2_bmc_ip = models.CharField(max_length=200, null=True, blank=True, verbose_name='두번째 노드 BMC IP')
    other_ips = models.TextField(blank=True, null=True, verbose_name='그 외 IP')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='삭제일시')

    class Meta:
        verbose_name_plural = "Install Base 관리"

    def __str__(self):
        return f"{self.cluster_name} - {self.customer.name}"

class ExpansionHistory(models.Model):
    install_base = models.ForeignKey(InstallBase, on_delete=models.CASCADE, related_name='expansions', verbose_name='해당 장비')
    expansion_date = models.DateField(verbose_name='증설 날짜')
    description = models.TextField(verbose_name='증설 내용')

    class Meta:
        verbose_name_plural = "증설 이력 관리"

    def __str__(self):
        return f"{self.install_base.cluster_name} - {self.expansion_date}"

class Issue(models.Model):
    ISSUE_TYPE_CHOICES = [
        ('part_replacement', '단순 파트 교체'),
        ('service_outage', '서비스 장애'),
        ('issue', '이슈'),
    ]
    
    STATUS_CHOICES = [
        ('진행중', '진행중'),
        ('종료', '종료'),
    ]

    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPE_CHOICES, verbose_name='이슈 타입')
    issue_date = models.DateField(verbose_name='이슈 발생 일자')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='진행중', verbose_name='진행 상태')
    title = models.CharField(max_length=200, verbose_name='이슈 제목')
    content = models.TextField(verbose_name='이슈 내용')
    end_date = models.DateField(null=True, blank=True, verbose_name='이슈 종료일')
    case_number = models.CharField(max_length=100, null=True, blank=True, verbose_name='케이스 번호')
    target_cluster = models.ForeignKey(InstallBase, on_delete=models.CASCADE, related_name='issues', null=True, blank=True, verbose_name='대상 클러스터')
    target_node = models.ForeignKey(InstallBase, on_delete=models.CASCADE, related_name='node_issues', null=True, blank=True, verbose_name='대상 노드')
    target_node_number = models.IntegerField(null=True, blank=True, help_text='1 또는 2 (node_name_1 또는 node_name_2)', verbose_name='대상 노드 번호')
    assigned_engineer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='이슈 진행자')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='삭제일시')

    class Meta:
        verbose_name_plural = "이슈 관리"

    def __str__(self):
        return f"{self.case_number or self.title} - {self.issue_date}"

class Part(models.Model):
    CATEGORY_CHOICES = [
        ('node', 'Node'),
        ('shelf', 'Shelf'),
        ('disk', 'Disk'),
    ]
    
    part_number = models.CharField(max_length=100, unique=True, verbose_name='파트 넘버')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='파트 종류')
    part_type = models.CharField(max_length=50, verbose_name='파트 타입')
    description = models.TextField(blank=True, verbose_name='파트 설명')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "파트 관리"

    def __str__(self):
        return f"{self.part_number} - {self.get_category_display()}"

class RMA(models.Model):
    RETURN_REQUIRED_CHOICES = [
        ('required', '반납 필요'),
        ('not_required', '반납 불필요'),
    ]
    
    RETURN_STATUS_CHOICES = [
        ('returned', '반납'),
        ('not_returned', '미반납'),
        ('not_required', '반납 불필요'),
    ]
    
    IS_DELAYED_CHOICES = [
        ('not_delivered', '배송 미완료'),
        ('delayed', '지연배송'),
        ('normal', '정상배송'),
    ]

    case_number = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='rmas', null=True, blank=True, verbose_name='케이스 번호')
    rma_number = models.CharField(max_length=100, verbose_name='RMA 번호')
    return_required = models.CharField(max_length=20, choices=RETURN_REQUIRED_CHOICES, default='required', verbose_name='반납 필요 여부')
    part = models.ForeignKey(Part, on_delete=models.PROTECT, verbose_name='파트 넘버')
    part_quantity = models.IntegerField(default=1, verbose_name='파트 수량')
    delivery_region = models.CharField(max_length=200, verbose_name='배송 지역')
    delivery_date = models.DateField(null=True, blank=True, verbose_name='배송 일자')
    return_region = models.CharField(max_length=200, null=True, blank=True, verbose_name='반납 지역')
    return_date = models.DateField(null=True, blank=True, verbose_name='반납 일자')
    is_delayed = models.CharField(max_length=20, choices=IS_DELAYED_CHOICES, default='not_delivered', verbose_name='지연 배송 여부')
    return_status = models.CharField(max_length=20, choices=RETURN_STATUS_CHOICES, default='not_returned', verbose_name='반납 여부')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='삭제일시')

    class Meta:
        verbose_name_plural = "RMA 관리"

    def __str__(self):
        return f"{self.rma_number} - {self.part.part_number}"

class NetAppAPIConfig(models.Model):
    """NetApp API 설정을 저장하는 모델 (싱글톤)"""
    ntap_uid = models.CharField(max_length=100, verbose_name="NTAP UID", blank=True)
    client_id = models.CharField(max_length=200, verbose_name="CLIENT ID", blank=True)
    client_secret = models.CharField(max_length=500, verbose_name="CLIENT SECRET", blank=True)
    last_test_serial = models.CharField(max_length=100, null=True, blank=True, verbose_name="마지막 테스트 시리얼 번호")
    last_test_date = models.DateTimeField(null=True, blank=True, verbose_name="마지막 테스트 일시")
    last_test_result = models.TextField(null=True, blank=True, verbose_name="마지막 테스트 결과")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "NetApp API 설정"
        verbose_name_plural = "NetApp API 설정"
    
    def __str__(self):
        return f"NetApp API Config (Updated: {self.updated_at})"
    
    @classmethod
    def get_config(cls):
        """싱글톤 패턴으로 설정 가져오기"""
        config, created = cls.objects.get_or_create(pk=1)
        return config

class UserProfile(models.Model):
    """사용자 프로필 모델"""
    RANK_CHOICES = [
        ('researcher', '연구원'),
        ('senior_researcher', '선임연구원'),
        ('chief_researcher', '책임연구원'),
        ('lead_researcher', '수석연구원'),
        ('team_leader', '팀장'),
        ('division_head', '사업부장'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile', verbose_name='사용자')
    avatar_seed = models.CharField(max_length=100, default='', blank=True, verbose_name='아바타 시드', help_text='DiceBear API에서 사용할 시드 값')
    rank = models.CharField(max_length=20, choices=RANK_CHOICES, default='researcher', verbose_name='직급')
    is_resigned = models.BooleanField(default=False, verbose_name='퇴사 여부')
    resigned_date = models.DateField(null=True, blank=True, verbose_name='퇴사일')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "사용자 프로필"
        verbose_name_plural = "사용자 프로필"

    def __str__(self):
        return f"{self.user.username} - Profile"
    
    def get_avatar_url(self):
        """DiceBear API를 사용한 아바타 URL 생성"""
        seed = self.avatar_seed or self.user.username
        return f"https://api.dicebear.com/7.x/avataaars/svg?seed={seed}"
    
    def get_rank_data(self):
        """직급별로 서로 다른 후광(Glow), 테두리(Border), 배지(Badge) 데이터를 반환합니다."""
        rank_map = {
            'researcher': {
                'level': 1, 
                'label': '연구원',
                'badge': '', 
                'glow_color': 'bg-slate-400',
                'border_color': '#e2e8f0',
                'glow_opacity': '0',
                'animation': ''
            },
            'senior_researcher': {
                'level': 2, 
                'label': '선임연구원',
                'badge': '🔹', 
                'glow_color': 'bg-sky-400',
                'border_color': '#38bdf8',
                'glow_opacity': '40',
                'animation': ''
            },
            'chief_researcher': {
                'level': 3, 
                'label': '책임연구원',
                'badge': '💠', 
                'glow_color': 'bg-indigo-500',
                'border_color': '#6366f1',
                'glow_opacity': '50',
                'animation': ''
            },
            'lead_researcher': {
                'level': 4, 
                'label': '수석연구원',
                'badge': '🔮', 
                'glow_color': 'bg-purple-600',
                'border_color': '#a855f7',
                'glow_opacity': '60',
                'animation': ''
            },
            'team_leader': {
                'level': 5, 
                'label': '팀장',
                'badge': '🔱', 
                'glow_color': 'bg-emerald-500',
                'border_color': 'transparent',
                'glow_opacity': '60',
                'animation': 'rank-glow-5'
            },
            'division_head': {
                'level': 6, 
                'label': '사업부장',
                'badge': '👑', 
                'glow_color': 'bg-amber-500',
                'border_color': 'transparent',
                'glow_opacity': '80',
                'animation': 'rank-glow-6'
            }
        }
        return rank_map.get(self.rank, rank_map['researcher'])
