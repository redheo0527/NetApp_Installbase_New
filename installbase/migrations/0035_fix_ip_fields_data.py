# Generated manually to fix IP field data

from django.db import migrations


def fix_invalid_ip_data(apps, schema_editor):
    """유효하지 않은 IP 데이터를 정리 (GenericIPAddressField에서 호환되지 않는 데이터 제거 또는 변환)"""
    InstallBase = apps.get_model('installbase', 'InstallBase')
    
    # SQL을 직접 사용하여 유효하지 않은 IP 데이터 처리
    with schema_editor.connection.cursor() as cursor:
        ip_fields = ['cluster_mgmt_ip', 'node1_mgmt_ip', 'node2_mgmt_ip', 'node1_bmc_ip', 'node2_bmc_ip']
        
        for field_name in ip_fields:
            try:
                # PostgreSQL에서 inet 타입 필드의 유효하지 않은 데이터를 찾아서 NULL로 설정
                # 또는 텍스트로 변환할 수 있는 값만 추출
                cursor.execute(f"""
                    UPDATE installbase_installbase 
                    SET {field_name} = NULL
                    WHERE {field_name}::text NOT SIMILAR TO '%([0-9]{1,3}\\.){3}[0-9]{1,3}%'
                """)
            except Exception as e:
                # 에러가 발생하면 해당 필드를 NULL로 설정
                print(f"Error fixing {field_name}: {e}")
                try:
                    cursor.execute(f"""
                        UPDATE installbase_installbase 
                        SET {field_name} = NULL
                        WHERE {field_name} IS NOT NULL
                    """)
                except:
                    pass


def reverse_fix_ip_data(apps, schema_editor):
    """역변환 함수 (필요하지 않음)"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('installbase', '0034_alter_installbase_cluster_mgmt_ip_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_invalid_ip_data, reverse_fix_ip_data),
    ]
