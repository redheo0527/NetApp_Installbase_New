from django.core.management.base import BaseCommand
from installbase.models import InstallBase, NetAppAPIConfig
import requests
import json
from datetime import datetime
from django.utils import timezone


class Command(BaseCommand):
    help = '매일 00:30에 실행되어 NetApp API로부터 계약 종료일을 업데이트합니다'

    def handle(self, *args, **options):
        self.stdout.write('계약 종료일 정보 업데이트 시작...')
        
        # API 설정 가져오기
        try:
            config = NetAppAPIConfig.get_config()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'API 설정을 가져올 수 없습니다: {e}'))
            return
        
        if not config.client_id or not config.client_secret or not config.ntap_uid:
            self.stdout.write(self.style.ERROR('API 설정이 완료되지 않았습니다.'))
            return
        
        # 삭제되지 않은 스토리지의 시리얼 번호 추출
        serial_numbers = InstallBase.objects.filter(
            deleted_at__isnull=True
        ).values_list('serial_number_1', flat=True).distinct()
        
        self.stdout.write(f'처리할 시리얼 번호 수: {serial_numbers.count()}')
        
        # 토큰 발급
        try:
            token_url = 'https://api.support.netapp.com/api/token'
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
                self.stdout.write(self.style.ERROR(f'토큰 발급 실패: {token_response.text}'))
                return
            
            token_data = token_response.json()
            token = token_data.get('token') or token_data.get('access_token')
            
            if not token:
                self.stdout.write(self.style.ERROR('토큰을 받을 수 없습니다.'))
                return
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'토큰 발급 중 오류: {e}'))
            return
        
        # 각 시리얼 번호에 대해 API 호출
        api_url = 'https://api.support.netapp.com/api/support/system-entitlements'
        updated_count = 0
        error_count = 0
        
        for serial_no in serial_numbers:
            if not serial_no:
                continue
            
            try:
                # API 호출
                api_response = requests.post(
                    api_url,
                    json={
                        'systemSerialNumber': serial_no,
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
                    self.stdout.write(self.style.WARNING(f'시리얼 {serial_no} API 호출 실패: {api_response.status_code}'))
                    error_count += 1
                    continue
                
                result_data = api_response.json()
                warranty_end_str = result_data.get('systemSerialNumberContractEndDate')
                
                if not warranty_end_str:
                    continue
                
                # 날짜 파싱 (DD-MM-YYYY -> YYYY-MM-DD 변환)
                try:
                    # DD-MM-YYYY 형식 파싱 (API 기본 형식)
                    contract_end_date = datetime.strptime(warranty_end_str, '%d-%m-%Y').date()
                except:
                    try:
                        # YYYY-MM-DD 형식 파싱 (이미 올바른 형식인 경우)
                        contract_end_date = datetime.strptime(warranty_end_str, '%Y-%m-%d').date()
                    except:
                        try:
                            # ISO 형식 파싱
                            contract_end_date = datetime.fromisoformat(warranty_end_str.replace('Z', '+00:00')).date()
                        except:
                            self.stdout.write(self.style.WARNING(f'시리얼 {serial_no} 날짜 파싱 실패: {warranty_end_str}'))
                            continue
                
                # 해당 시리얼 번호를 가진 모든 InstallBase 업데이트
                installbases = InstallBase.objects.filter(
                    serial_number_1=serial_no,
                    deleted_at__isnull=True
                )
                
                for ib in installbases:
                    if ib.contract_end_date != contract_end_date:
                        ib.contract_end_date = contract_end_date
                        ib.save(update_fields=['contract_end_date'])
                        updated_count += 1
                        self.stdout.write(f'업데이트: {serial_no} -> {contract_end_date}')
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'시리얼 {serial_no} 처리 중 오류: {e}'))
                error_count += 1
                continue
        
        self.stdout.write(self.style.SUCCESS(f'완료! 업데이트: {updated_count}개, 오류: {error_count}개'))
