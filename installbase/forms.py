from django import forms
from .models import InstallBase, ClusterSwitch, SwitchModel, Issue, RMA, Part

class InstallBaseForm(forms.ModelForm):
    class Meta:
        model = InstallBase
        fields = '__all__'

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
        super().__init__(*args, **kwargs)
        if target_node_id:
            self.fields['target_node'].initial = target_node_id
    
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
    
    class Meta:
        model = RMA
        fields = '__all__'

class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = '__all__'
