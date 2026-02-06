from django import forms
from django.forms import DateInput
from .models import InstallBase, ClusterSwitch, SwitchModel, Issue, RMA, Part

class InstallBaseForm(forms.ModelForm):
    class Meta:
        model = InstallBase
        fields = '__all__'
        widgets = {
            'install_date': DateInput(attrs={'type': 'date'}),
            'contract_end_date': DateInput(attrs={'type': 'date'}),
            'maintenance_start': DateInput(attrs={'type': 'date'}),
            'maintenance_end': DateInput(attrs={'type': 'date'}),
        }

class ClusterSwitchForm(forms.ModelForm):
    class Meta:
        model = ClusterSwitch
        fields = '__all__'

class SwitchModelForm(forms.ModelForm):
    class Meta:
        model = SwitchModel
        fields = '__all__'

class IssueForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        target_node_id = kwargs.pop('target_node_id', None)
        target_cluster_id = kwargs.pop('target_cluster_id', None)
        super().__init__(*args, **kwargs)
        if target_node_id:
            self.fields['target_node'].initial = target_node_id
        if target_cluster_id:
            self.fields['target_cluster'].initial = target_cluster_id
    
    class Meta:
        model = Issue
        fields = '__all__'

class RMAForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        case_number_id = kwargs.pop('case_number_id', None)
        super().__init__(*args, **kwargs)
        if case_number_id:
            self.fields['case_number'].initial = case_number_id
        # return_required를 optional로 설정
        self.fields['return_required'].required = False
        # return_status도 optional로 설정 (return_required가 not_required일 때 자동 설정)
        self.fields['return_status'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        # return_required가 'not_required'이면 return_status도 'not_required'로 설정
        return_required = cleaned_data.get('return_required')
        if return_required == 'not_required':
            cleaned_data['return_status'] = 'not_required'
        return cleaned_data
    
    class Meta:
        model = RMA
        fields = '__all__'

class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = '__all__'
