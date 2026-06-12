from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from decimal import Decimal
from .models import (
    CustomUser, 
    PlatformSettings, 
    Level, 
    BankDetails, 
    Deposit, 
    Withdrawal, 
    Task, 
    Roulette, 
    RouletteSettings, 
    UserLevel, 
    PlatformBankDetails
)

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        'phone_number', 
        'available_balance', 
        'get_afiliados_count', 
        'get_investidores_count',
        'get_tarefas_estagiario',
        'is_staff', 
        'is_active', 
        'date_joined'
    )
    search_fields = ('phone_number', 'invite_code')
    list_filter = ('is_staff', 'is_active', 'level_active', 'is_intern_expired')

    def get_afiliados_count(self, obj):
        return CustomUser.objects.filter(invited_by=obj).count()
    get_afiliados_count.short_description = 'Convidados'

    def get_investidores_count(self, obj):
        return CustomUser.objects.filter(invited_by=obj, userlevel__is_active=True).distinct().count()
    get_investidores_count.short_description = 'Investidores'

    def get_tarefas_estagiario(self, obj):
        count = Task.objects.filter(user=obj).count()
        if obj.level_active:
            return mark_safe(f'<span style="color: #28a745; font-weight: bold;">VIP ({count})</span>')
        return f"{count} / 2"
    get_tarefas_estagiario.short_description = 'Tarefas (Estag.)'


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'whatsapp_link', 'history_text', 'deposit_instruction', 'withdrawal_instruction')
    search_fields = ('whatsapp_link',)


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'deposit_value', 'daily_gain', 'monthly_gain', 'cycle_days')
    search_fields = ('name',)


@admin.register(BankDetails)
class BankDetailsAdmin(admin.ModelAdmin):
    # Mudança inteligente: Exibe dinamicamente na lista se a conta é USDT ou dados bancários normais
    list_display = ('user', 'get_tipo_conta', 'bank_name', 'account_holder_name', 'IBAN')
    search_fields = ('user__phone_number', 'bank_name', 'account_holder_name', 'IBAN')

    def get_tipo_conta(self, obj):
        if obj.IBAN and not obj.bank_name and not obj.account_holder_name:
            return mark_safe('<b style="color: #16a34a;">Carteira USDT</b>')
        elif getattr(obj, 'type', None) == 'USDT':
            return mark_safe('<b style="color: #16a34a;">Carteira USDT</b>')
        return mark_safe('<b style="color: #ef4444;">Banco Kwanza</b>')
    get_tipo_conta.short_description = 'Tipo de Conta'


@admin.register(PlatformBankDetails)
class PlatformBankDetailsAdmin(admin.ModelAdmin):
    list_display = ('get_type_icon', 'bank_name', 'account_holder_name', 'IBAN_preview')
    list_filter = ('type', 'bank_name')
    search_fields = ('bank_name', 'account_holder_name', 'IBAN')
    
    fieldsets = (
        ('Configuração do Canal de Recebimento', {
            'fields': ('type',),
            'description': 'Escolha o ecossistema financeiro desta conta para direcionamento automático no front-end.'
        }),
        ('Coordenadas de Destino (Depósito)', {
            'fields': ('bank_name', 'account_holder_name', 'IBAN'),
            'description': 'Para Kwanza, use o nome do Banco e o IBAN. Para USDT, insira apenas a Rede (Ex: TRC-20) e o Endereço no campo IBAN.'
        }),
    )

    def get_type_icon(self, obj):
        if obj.type == 'PIX' or obj.type == 'KWANZA':  
            return mark_safe(
                '<span style="background: #ef4444; color: #fff; padding: 4px 10px; '
                'border-radius: 12px; font-size: 11px; font-weight: 700; display: inline-block;">'
                '<i class="fa-solid fa-money-bill-wave" style="margin-right: 4px;"></i> KWANZA (AOA)</span>'
            )
        return mark_safe(
            '<span style="background: #16a34a; color: #fff; padding: 4px 10px; '
            'border-radius: 12px; font-size: 11px; font-weight: 700; display: inline-block;">'
            '<i class="fa-solid fa-circle-dollar-to-slot" style="margin-right: 4px;"></i> USDT (Cripto)</span>'
        )
    get_type_icon.short_description = 'Canal / Moeda'

    def IBAN_preview(self, obj):
        if obj.IBAN:
            preview = obj.IBAN[:24] + "..." if len(obj.IBAN) > 24 else obj.IBAN
            return mark_safe(f'<code style="font-family: monospace; font-size: 12px;">{preview}</code>')
        return "-"
    IBAN_preview.short_description = 'Endereço da Carteira / IBAN'

    class Media:
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',)
        }


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'is_approved', 'created_at', 'proof_link') 
    search_fields = ('user__phone_number',)
    list_filter = ('is_approved',)
    readonly_fields = ('current_proof_display',)

    def save_model(self, request, obj, form, change):
        if change:
            old_deposit = Deposit.objects.get(pk=obj.pk)
            if not old_deposit.is_approved and obj.is_approved:
                user = obj.user
                user.available_balance += obj.amount
                user.save()
                messages.success(request, f"Saldo de {obj.amount} creditado para {user.phone_number}")
        super().save_model(request, obj, form, change)

    def proof_link(self, obj):
        if obj.proof_of_payment:
            return mark_safe(f'<a href="{obj.proof_of_payment.url}" target="_blank">Ver Comprovativo</a>')
        return "Nenhum"
    proof_link.short_description = 'Comprovativo'

    def current_proof_display(self, obj):
        if obj.proof_of_payment:
            return mark_safe(f'''
                <a href="{obj.proof_of_payment.url}" target="_blank">Ver Imagem em Tamanho Real</a><br/>
                <img src="{obj.proof_of_payment.url}" style="max-width:300px; height:auto; margin-top: 10px;" />
            ''')
        return "Nenhum Comprovativo Carregado"
    current_proof_display.short_description = 'Comprovativo Atual'


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = (
        'user', 
        'get_canal_solicitado', 
        'get_valor_bruto_kz', 
        'get_taxa_descontada_kz',
        'get_valor_liquido_kz', 
        'get_iban_direto', 
        'status', 
        'botao_aprovar_rapido'
    )
    
    list_filter = ('status', 'created_at', 'channel_type')
    search_fields = ('user__phone_number', 'user__full_name', 'user__username', 'bank_iban', 'crypto_address')

    readonly_fields = (
        'get_canal_solicitado',
        'get_valor_bruto_kz', 
        'get_taxa_descontada_kz', 
        'get_valor_liquido_kz', 
        'get_dados_bancarios',
        'created_at'
    )

    fieldsets = (
        ('Informações do Cliente', {
            'fields': ('user', 'status', 'created_at')
        }),
        ('Cálculos de Auditoria (Desconto de Taxa Integrado)', {
            'fields': (
                'get_canal_solicitado',
                'get_valor_bruto_kz', 
                'get_taxa_descontada_kz', 
                'get_valor_liquido_kz'
            )
        }),
        ('Logística e Destino do Pagamento', {
            'fields': ('get_dados_bancarios',)
        }),
        ('Dados Técnicos', {
            'fields': ('amount',),
            'classes': ('collapse',),
        }),
    )
    
    TAXA_PERCENTUAL = Decimal('0.10')

    def get_canal_solicitado(self, obj):
        """ Verifica o canal real gravado no momento em que o saque foi efetuado """
        canal = getattr(obj, 'channel_type', 'KWANZA')
        if canal == 'USDT':
            return mark_safe('<span style="color: #16a34a; font-weight: bold;"><i class="fa-solid fa-circle-dollar-to-slot"></i> USDT</span>')
        return mark_safe('<span style="color: #ef4444; font-weight: bold;"><i class="fa-solid fa-money-bill-wave"></i> KWANZA (AOA)</span>')
    get_canal_solicitado.short_description = 'Canal / Moeda'

    def get_valor_bruto_kz(self, obj):
        return f"{obj.amount:,.2f} Kz".replace(",", "X").replace(".", ",").replace("X", ".")
    get_valor_bruto_kz.short_description = 'Bruto'

    def get_taxa_descontada_kz(self, obj):
        taxa = obj.amount * self.TAXA_PERCENTUAL
        taxa_formatada = f"{taxa:,.2f} Kz".replace(",", "X").replace(".", ",").replace("X", ".")
        return mark_safe(f'<span style="color: #dc2626; font-weight: 500;">- {taxa_formatada}</span>')
    get_taxa_descontada_kz.short_description = 'Taxa (10%)'

    def get_valor_liquido_kz(self, obj):
        liquido = obj.amount * (Decimal('1') - self.TAXA_PERCENTUAL)
        liquido_formatado = f"{liquido:,.2f} Kz".replace(",", "X").replace(".", ",").replace("X", ".")
        return mark_safe(f'<b style="color: #0f172a; font-size: 13px;">{liquido_formatado}</b>')
    get_valor_liquido_kz.short_description = 'Líquido'

    def get_iban_direto(self, obj):
        """ Retorna diretamente o dado fixado no registro histórico do saque """
        canal = getattr(obj, 'channel_type', 'KWANZA')
        if canal == 'USDT':
            endereco = getattr(obj, 'crypto_address', 'Sem Endereço') or 'Sem Endereço'
            return mark_safe(f'<code style="color:#16a34a; font-weight:600; font-family: monospace;">{endereco}</code>')
        
        iban = getattr(obj, 'bank_iban', 'Sem IBAN') or 'Sem IBAN'
        return mark_safe(f'<code style="color:#2563eb; font-weight:600; font-family: monospace;">{iban}</code>')
    get_iban_direto.short_description = 'IBAN / Carteira USDT'

    def get_dados_bancarios(self, obj):
        """ Renderiza os blocos com base exclusiva nos dados imutáveis salvos no registro do saque """
        canal = getattr(obj, 'channel_type', 'KWANZA')
        
        if canal == 'USDT':
            rede = getattr(obj, 'usdt_network', 'Não informada') or 'Não informada'
            carteira = getattr(obj, 'crypto_address', 'Não informada') or 'Não informada'
            return mark_safe(
                f"<div style='background:#f0fdf4; padding:12px 16px; border-radius:12px; border:1px solid #bbf7d0; max-width: 400px;'>\n"
                f"<span style='font-size:11px; text-transform:uppercase; color:#16a34a; font-weight:700; display:block; margin-bottom:4px;'>Destinatário Cripto (USDT)</span>"
                f"<b>Rede:</b> {rede}<br>"
                f"<b>Endereço da Carteira:</b> <code style='font-family:monospace; font-size:12px; color:#16a34a; font-weight:bold;'>{carteira}</code>"
                f"</div>"
            )
            
        # Layout Completo para saques em Kwanza (Angola)
        titular = getattr(obj, 'bank_holder', 'Não informado') or 'Não informado'
        banco = getattr(obj, 'bank_name', 'Não informado') or 'Não informado'
        iban = getattr(obj, 'bank_iban', 'Não informado') or 'Não informado'
        return mark_safe(
            f"<div style='background:#f8fafc; padding:12px 16px; border-radius:12px; border:1px solid #e2e8f0; max-width: 400px;'>"
            f"<span style='font-size:11px; text-transform:uppercase; color:#64748b; font-weight:700; display:block; margin-bottom:4px;'>Destinatário Bancário (Kwanza)</span>"
            f"<b>Titular:</b> {titular}<br>"
            f"<b>Banco:</b> {banco}<br>"
            f"<b>IBAN:</b> <code style='font-family:monospace; font-size:12px; color:#2563eb;'>{iban}</code>"
            f"</div>"
        )
    get_dados_bancarios.short_description = 'Coordenadas de Envio'

    def botao_aprovar_rapido(self, obj):
        if obj.status in ['Pendente', 'Pending']:
            return mark_safe(
                f'<a class="button" href="?set_status=Aprovado&idx={obj.id}" '
                f'style="background-color: #16a34a; color: white; padding: 6px 12px; border-radius: 6px; '
                f'text-decoration: none; font-weight: 700; font-size: 11px; display: inline-block;">'
                f'Aprovar e Pagar</a>'
            )
        elif obj.status in ['Aprovado', 'Approved']:
            return mark_safe("<span style='color:#16a34a; font-weight:700;'><i class='fa-solid fa-circle-check'></i> Pago</span>")
        return mark_safe(f"<span style='color:#64748b;'>{obj.status}</span>")
    botao_aprovar_rapido.short_description = 'Ações'

    def changelist_view(self, request, extra_context=None):
        if 'set_status' in request.GET and 'idx' in request.GET:
            status_novo = request.GET.get('set_status')
            idx = request.GET.get('idx')
            
            withdrawal = Withdrawal.objects.filter(id=idx).first()
            if withdrawal and withdrawal.status in ['Pendente', 'Pending']:
                withdrawal.status = status_novo
                withdrawal.save()
                self.message_user(request, f"Saque de {withdrawal.user.get_username()} aprovado com sucesso.")
                
        return super().changelist_view(request, extra_context)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('user', 'earnings', 'completed_at')
    search_fields = ('user__phone_number',)


@admin.register(Roulette)
class RouletteAdmin(admin.ModelAdmin):
    list_display = ('user', 'prize', 'is_approved', 'spin_date')
    search_fields = ('user__phone_number',)
    list_filter = ('is_approved',)


@admin.register(RouletteSettings)
class RouletteSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'prizes')


@admin.register(UserLevel)
class UserLevelAdmin(admin.ModelAdmin):
    list_display = ('user', 'level', 'purchase_date', 'is_active')
    search_fields = ('user__phone_number', 'level__name')
    list_filter = ('is_active',)
    