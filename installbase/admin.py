from django.contrib import admin
from .models import (
    Product,
    SwitchModel,
    ClusterSwitch,
    InstallBase,
    ExpansionHistory,
    Part,
    Issue,
    RMA,
)

# 1. 장비 모델 관리
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("lineup", "model_name")
    list_filter = ("lineup",)
    search_fields = ("model_name",)


# 2. 스위치 모델 관리
@admin.register(SwitchModel)
class SwitchModelAdmin(admin.ModelAdmin):
    list_display = ("model_name",)
    search_fields = ("model_name",)

# 3. 클러스터 스위치 관리
@admin.register(ClusterSwitch)
class ClusterSwitchAdmin(admin.ModelAdmin):
    list_display = ("switch_name_1", "switch_name_2", "switch_model_1", "switch_model_2", "serial_number_1", "serial_number_2")
    search_fields = ("switch_name_1", "switch_name_2", "serial_number_1", "serial_number_2", "switch_model_1__model_name", "switch_model_2__model_name")


# 4. Install Base (핵심)
@admin.register(InstallBase)
class InstallBaseAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "cluster_name",
        "service_name",
        "product",
        "service_level",
        "is_switch_connected",
        "maintenance_end",
    )

    list_filter = (
        "service_level",
        "periodic_inspection",
        "is_switch_connected",
    )

    search_fields = (
        "customer",
        "cluster_name",
        "serial_number_1",
        "serial_number_2",
    )

    filter_horizontal = ("assigned_engineers",)


# 5. 증설 이력
@admin.register(ExpansionHistory)
class ExpansionHistoryAdmin(admin.ModelAdmin):
    list_display = ("install_base", "expansion_date")
    search_fields = ("install_base__cluster_name",)

# 6. 파트 관리
@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("part_number", "category", "part_type", "description")
    list_filter = ("category", "part_type")
    search_fields = ("part_number", "description")

# 7. 이슈 관리
@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("title", "target_cluster", "target_node", "issue_type", "status", "issue_date", "case_number")
    list_filter = ("issue_type", "status", "issue_date")
    search_fields = ("title", "content", "case_number", "target_cluster__cluster_name")# 8. RMA 관리
@admin.register(RMA)
class RMAAdmin(admin.ModelAdmin):
    list_display = ("rma_number", "case_number", "part", "part_quantity", "delivery_region", "delivery_date", "return_status")
    list_filter = ("return_required", "is_delayed", "return_status")
    search_fields = ("rma_number", "part__part_number", "case_number__case_number")
