from .models import UserProfile

def user_profile(request):
    """모든 템플릿에서 user.profile에 안전하게 접근할 수 있도록 context 제공"""
    context = {}
    if request.user.is_authenticated:
        try:
            context['user_profile'] = request.user.profile
        except UserProfile.DoesNotExist:
            # UserProfile이 없으면 자동으로 생성
            context['user_profile'] = UserProfile.objects.create(user=request.user)
    return context
