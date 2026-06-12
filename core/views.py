from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import random
from datetime import date, time, datetime
from django.utils import timezone
import pytz  # <--- ADICIONE ESTA LINHA AQUI
from decimal import Decimal

from .forms import RegisterForm, DepositForm, WithdrawalForm, BankDetailsForm
from .models import PlatformSettings, CustomUser, Level, UserLevel, BankDetails, Deposit, Withdrawal, Task, PlatformBankDetails, Roulette, RouletteSettings

# --- FUNÇÃO HOME ---
def home(request):
    if request.user.is_authenticated:
        return redirect('menu')
    else:
        return redirect('cadastro')

# --- FUNÇÃO MENU ---
@login_required
def menu(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or 0
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or 0
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or 0

    try:
        platform_settings = PlatformSettings.objects.first()
        whatsapp_link = platform_settings.whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'

    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'whatsapp_link': whatsapp_link,
    }
    return render(request, 'menu.html', context)

# --- CADASTRO (REMOVIDO 1000 KZ) ---
def cadastro(request):
    invite_code_from_url = request.GET.get('invite', None)
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            
            # SALDO INICIAL DEFINIDO COMO 0 CONFORME PEDIDO
            user.available_balance = 0 
            
            invited_by_code = form.cleaned_data.get('invited_by_code')
            if invited_by_code:
                try:
                    invited_by_user = CustomUser.objects.get(invite_code=invited_by_code)
                    user.invited_by = invited_by_user
                except CustomUser.DoesNotExist:
                    messages.error(request, 'Código de convite inválido.')
                    return render(request, 'cadastro.html', {'form': form})
            
            user.save()
            login(request, user)
            messages.success(request, 'Cadastro realizado com sucesso!')
            return redirect('menu')
    else:
        form = RegisterForm(initial={'invited_by_code': invite_code_from_url}) if invite_code_from_url else RegisterForm()
    
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'
    return render(request, 'cadastro.html', {'form': form, 'whatsapp_link': whatsapp_link})

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('menu')
    else:
        form = AuthenticationForm()
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'
    return render(request, 'login.html', {'form': form, 'whatsapp_link': whatsapp_link})

@login_required
def user_logout(request):
    logout(request)
    return redirect('menu')

# --- DEPÓSITO INTERNACIONAL (USDT / KWANZA) ---
@login_required
def deposito(request):
    # Filtra as contas do tipo correspondente cadastradas no Admin do Django
    pix_accounts = PlatformBankDetails.objects.filter(type='PIX')
    usdt_wallets = PlatformBankDetails.objects.filter(type='USDT')
    
    settings = PlatformSettings.objects.first()
    deposit_instruction = settings.deposit_instruction if settings else ''
    
    # Coleta valores únicos dos níveis e ordena de forma crescente
    level_deposits = Level.objects.all().values_list('deposit_value', flat=True).distinct().order_by('deposit_value')
    # Mantemos como float/int limpo para o motor JavaScript ler nativamente sem quebras de string
    level_deposits_list = [float(d) for d in level_deposits] 

    if request.method == 'POST':
        form = DepositForm(request.POST, request.FILES)
        if form.is_valid():
            deposit = form.save(commit=False)
            deposit.user = request.user
            
            # Captura a moeda vinda do front-end (USDT ou KWANZA)
            currency_type = request.POST.get('currency_type', 'KWANZA')
            payment_channel = request.POST.get('payment_method', 'Não Especificado')
            
            # Customização inteligente da descrição do método de pagamento
            # Salvando explicitamente o tipo de ativo usado para facilitar a auditoria da equipe
            deposit.payment_method = f"[{currency_type}] {payment_channel}"
            
            # Captura o valor final enviado (Garantindo conversão segura para Decimal)
            raw_amount = request.POST.get('amount', '0')
            try:
                deposit.amount = Decimal(raw_amount)
            except:
                deposit.amount = Decimal('0.00')

            if deposit.amount > 0:
                deposit.save()
                return render(request, 'deposito.html', {'deposit_success': True})
            else:
                messages.error(request, 'O valor do depósito deve ser maior que zero.')
        else:
            # Caso o formulário falhe em alguma validação interna do Django
            messages.error(request, 'Erro ao processar os dados do depósito. Verifique os campos e o comprovante.')
    
    else:
        form = DepositForm()
        
    context = {
        'pix_accounts': pix_accounts,
        'usdt_wallets': usdt_wallets,
        'form': form,
        'level_deposits_list': level_deposits_list,
        'deposit_success': False,
    }
    return render(request, 'deposito.html', context)


# --- APROVAÇÃO DE DEPÓSITO (PAINEL DE ADMINISTRAÇÃO / STAFF) ---
@login_required
def approve_deposit(request, deposit_id):
    if not request.user.is_staff:
        return redirect('menu')
        
    deposit = get_object_or_404(Deposit, id=deposit_id)
    
    if not deposit.is_approved:
        deposit.is_approved = True
        deposit.save()
        
        # Adiciona o saldo diretamente na carteira unificada do usuário em Kwanza
        # Como o front-end já envia o valor de USDT convertido para a equivalência em Kwanza, 
        # o saldo é incrementado perfeitamente sem distorções cambiais.
        deposit.user.available_balance += deposit.amount
        deposit.user.save()
        
        messages.success(request, f'Depósito de {deposit.amount} Kz aprovado com sucesso para {deposit.user.username}.')
        
    return redirect('renda')

@login_required
def saque(request):
    # --- CONFIGURAÇÕES DE REGRAS DE NEGÓCIO ---
    MIN_WITHDRAWAL_KWANZA = Decimal('2000')
    MIN_WITHDRAWAL_USDT = Decimal('2')
    TAXA_SAQUE = Decimal('0.10')  
    
    # Taxa de conversão: 1 USDT = 1000 Kz (Ajuste este valor se necessário)
    TAXA_CAMBIO_USDT_K_Z = Decimal('1000') 
    CAMBIO_BRL_WISE = Decimal('0.0065') 
    
    # Configuração de Fuso Horário de Luanda (UTC+1)
    luanda_tz = pytz.timezone('Africa/Luanda')
    now_luanda = timezone.now().astimezone(luanda_tz)
    current_weekday = now_luanda.weekday() # 0=Segunda, 5=Sábado, 6=Domingo
    
    # Regra: Permitido de Segunda a Sábado, 24 horas por dia (24/24)
    is_working_day = current_weekday <= 5

    # --- DADOS DA PLATAFORMA ---
    settings = PlatformSettings.objects.first()
    withdrawal_instruction = settings.withdrawal_instruction if settings else ''
    withdrawal_records = Withdrawal.objects.filter(user=request.user).order_by('-created_at')
    
    # Processamento para exibição no Histórico
    for record in withdrawal_records:
        valor_liquido_kz = record.amount * (Decimal('1') - TAXA_SAQUE)
        record.amount_brl = valor_liquido_kz * CAMBIO_BRL_WISE
        record.liquido_display = valor_liquido_kz

    today = now_luanda.date()
    
    # Limite estrito de 1 saque por dia
    withdrawals_today_count = Withdrawal.objects.filter(
        user=request.user, 
        created_at__date=today
    ).count()
    
    can_withdraw_today = withdrawals_today_count == 0
    
    # --- PROCESSAMENTO DO POST ---
    if request.method == 'POST':
        # Captura o canal selecionado no front-end ('USDT' ou 'KWANZA')
        chosen_channel = request.POST.get('chosen_channel', 'KWANZA').upper()
        raw_amount = request.POST.get('amount')
        
        try:
            amount_input = Decimal(str(raw_amount))
        except (ValueError, TypeError, KeyError):
            messages.error(request, 'Valor inserido inválido.')
            return redirect('saque')

        # Transforma o valor inserido para a moeda padrão do Banco de Dados (Kwanza) para processar o débito
        if chosen_channel == 'USDT':
            amount_bruto_kz = amount_input * TAXA_CAMBIO_USDT_K_Z
        else:
            amount_bruto_kz = amount_input

        # --- VALIDAÇÕES DE SEGURANÇA ---
        if not is_working_day:
            messages.error(request, 'Os saques estão disponíveis apenas de Segunda a Sábado.')
            
        elif not can_withdraw_today:
            messages.error(request, 'Você já realizou uma solicitação hoje. Limite máximo: 1 saque por dia.')
            
        # Validação do valor mínimo com base no canal escolhido
        elif chosen_channel == 'USDT' and amount_input < MIN_WITHDRAWAL_USDT:
            messages.error(request, f'O valor mínimo para saque via USDT é de {MIN_WITHDRAWAL_USDT} USDT.')
            
        elif chosen_channel == 'KWANZA' and amount_input < MIN_WITHDRAWAL_KWANZA:
            messages.error(request, f'O valor mínimo para saque via Kwanza é de {MIN_WITHDRAWAL_KWANZA} Kz.')
            
        # Validação de Saldo na conta do usuário (Sempre validado em Kz)
        elif request.user.available_balance < amount_bruto_kz:
            messages.error(request, 'Saldo insuficiente para completar esta operação.')
            
        else:
            # Tudo validado! Realiza os cálculos de liquidação
            valor_liquido_kz = amount_bruto_kz * (Decimal('1') - TAXA_SAQUE)
            
            # --- CAPTURA DAS COORDENADAS DO FORMULÁRIO HTML ---
            usdt_network = request.POST.get('usdt_network', '').strip()
            crypto_address = request.POST.get('crypto_address', '').strip()
            bank_holder = request.POST.get('bank_holder', '').strip()
            bank_name = request.POST.get('bank_name', '').strip()
            bank_iban = request.POST.get('bank_iban', '').strip()
            
            # Salva o registro de saque no banco de dados com as coordenadas inseridas
            nova_retirada = Withdrawal.objects.create(
                user=request.user, 
                amount=amount_input,
                channel_type=chosen_channel,
                usdt_network=usdt_network if chosen_channel == 'USDT' else None,
                crypto_address=crypto_address if chosen_channel == 'USDT' else None,
                bank_holder=bank_holder if chosen_channel == 'KWANZA' else None,
                bank_name=bank_name if chosen_channel == 'KWANZA' else None,
                bank_iban=bank_iban if chosen_channel == 'KWANZA' else None
            )
            
            # Mantida a verificação dinâmica caso o campo exista isolado
            if hasattr(nova_retirada, 'channel_type'):
                nova_retirada.channel_type = chosen_channel
                nova_retirada.save()

            # Deduz o valor bruto em Kwanzas do saldo do usuário
            request.user.available_balance -= amount_bruto_kz
            request.user.save()
            
            # Mensagem de retorno adaptada ao canal escolhido
            if chosen_channel == 'USDT':
                valor_liquido_usdt = amount_input * (Decimal('1') - TAXA_SAQUE)
                messages.success(request, f'Saque de {valor_liquido_usdt:.2f} USDT solicitado com sucesso! Processamento ativo.')
            else:
                messages.success(request, f'Saque de {valor_liquido_kz:.2f} Kz solicitado com sucesso! Aguarde o processamento bancário.')
                
            return redirect('saque')

    context = {
        'withdrawal_instruction': withdrawal_instruction,
        'withdrawal_records': withdrawal_records,
        'has_withdrawn_today': not can_withdraw_today, 
        'is_time_to_withdraw': is_working_day,  
    }
    return render(request, 'saque.html', context)
    
# --- FUNÇÃO AUXILIAR DE COMISSÃO ---
def distribuir_comissao_tarefa(user, ganho_tarefa):
    """
    Distribui comissão para os convidados (Upline)
    Nível A: 5% | Nível B: 2% | Nível C: 1%
    """
    percentuais = [
        (Decimal('0.05')), # Nível A
        (Decimal('0.02')), # Nível B
        (Decimal('0.01')), # Nível C
    ]
    
    # AJUSTADO: Usando 'invited_by' conforme seu código de cadastro
    current_upline = getattr(user, 'invited_by', None)
    
    for pct in percentuais:
        if current_upline:
            # Apenas paga comissão se o UPLINE tiver pelo menos um VIP ativo
            upline_tem_vip = UserLevel.objects.filter(user=current_upline, is_active=True).exists()
            
            if upline_tem_vip:
                comissao = ganho_tarefa * pct
                current_upline.available_balance += comissao
                # Opcional: registrar no subsidy_balance para aparecer na tela de Equipa
                current_upline.subsidy_balance += comissao 
                current_upline.save()
            
            # Passa para o próximo nível
            current_upline = getattr(current_upline, 'invited_by', None)
        else:
            break

@login_required
def tarefa(request):
    user = request.user
    today = timezone.localdate()
    
    # 1. Status VIP
    active_user_levels = UserLevel.objects.filter(user=user, is_active=True).select_related('level')
    has_active_level = active_user_levels.exists()
    
    # 2. Histórico e Contagem
    total_tasks_ever = Task.objects.filter(user=user).count()
    tasks_completed_today = Task.objects.filter(user=user, completed_at__date=today).count()
    
    # 3. Lógica de Estagiário Protegida (Estágio Removido)
    is_intern = False

    # 4. Variável mestre para o Botão do HTML (Apenas VIP faz tarefa)
    can_do_task = has_active_level and tasks_completed_today < 1

    context = {
        'has_active_level': has_active_level,
        'is_intern': is_intern,
        'can_do_task': can_do_task,
        'tasks_completed_today': tasks_completed_today,
        'total_tasks_ever': total_tasks_ever,
        'is_intern_expired': user.is_intern_expired,
    }
    return render(request, 'tarefa.html', context)

@login_required
@require_POST
def process_task(request):
    user = request.user
    today = timezone.localdate()
    
    try:
        # Bloqueio 1: Já fez a tarefa de hoje?
        if Task.objects.filter(user=user, completed_at__date=today).exists():
            return JsonResponse({'success': False, 'message': 'Você já realizou a tarefa de hoje.'})

        active_user_levels = UserLevel.objects.filter(user=user, is_active=True).select_related('level')
        total_tasks_ever = Task.objects.filter(user=user).count()
        
        total_task_earnings = Decimal('0.00')
        is_vip_task = False

        # LÓGICA DE VERIFICAÇÃO (Sem estágio, apenas VIP)
        if active_user_levels.exists():
            is_vip_task = True
            for user_level in active_user_levels:
                total_task_earnings += Decimal(str(user_level.level.daily_gain))
        else:
            return JsonResponse({
                'success': False, 
                'message': 'Ative um VIP para continuar a lucrar.'
            })

        # Salva a tarefa e paga o usuário
        Task.objects.create(user=user, earnings=total_task_earnings)
        user.available_balance += total_task_earnings
        user.save() 

        # Distribui comissão apenas se for VIP
        if is_vip_task:
            distribui_comissao_tarefa(user, total_task_earnings)
        
        return JsonResponse({
            'success': True, 
            'message': f'Sucesso! Você recebeu {total_task_earnings} KZ.'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro: {str(e)}'})
        
@login_required
def nivel(request):
    if request.method == 'POST':
        level_id = request.POST.get('level_id')
        level_to_buy = get_object_or_404(Level, id=level_id)
        val = level_to_buy.deposit_value

        user_levels = UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True)
        if level_to_buy.id in user_levels:
            messages.error(request, 'Você já possui este nível.')
            return redirect('nivel')

        if request.user.available_balance >= val:
            request.user.available_balance -= val
            UserLevel.objects.create(user=request.user, level=level_to_buy, is_active=True)
            request.user.level_active = True
            request.user.save()

            # Nível A (10%)
            p1 = request.user.invited_by
            if p1 and UserLevel.objects.filter(user=p1, is_active=True).exists():
                com1 = val * Decimal('0.10')
                p1.available_balance += com1
                p1.subsidy_balance += com1
                p1.save()

                # Nível B (1%)
                p2 = p1.invited_by
                if p2 and UserLevel.objects.filter(user=p2, is_active=True).exists():
                    com2 = val * Decimal('0.01')  # Ajustado para 1% conforme seu comentário anterior (0.01)
                    p2.available_balance += com2
                    p2.subsidy_balance += com2
                    p2.save()

                    # Nível C (1%)
                    p3 = p2.invited_by
                    if p3 and UserLevel.objects.filter(user=p3, is_active=True).exists():
                        com3 = val * Decimal('0.01')
                        p3.available_balance += com3
                        p3.subsidy_balance += com3
                        p3.save()

            messages.success(request, f'Nível {level_to_buy.name} ativado!')
        else:
            messages.error(request, 'Saldo insuficiente.')
        return redirect('nivel')
    
    # --- LOGICA DE BUSCA E CÁLCULO DOS VALORES DOS CARDS ---
    raw_levels = Level.objects.all().order_by('deposit_value')
    processed_levels = []
    
    for level in raw_levels:
        # Cálculos Dinâmicos com base no ganho diário
        daily = level.daily_gain or Decimal('0.00')
        monthly_gain = daily * 30
        yearly_gain = daily * 365
        
        # Injeta os valores calculados diretamente no objeto que vai para o HTML
        level.monthly_gain = monthly_gain
        level.yearly_gain = yearly_gain
        processed_levels.append(level)
        
    context = {
        'levels': processed_levels,
        # CORREÇÃO AQUI: Adicionado o parâmetro 'user=' para corrigir o TypeError
        'user_levels': UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True),
    }
    return render(request, 'nivel.html', context)

@login_required
def equipa(request):
    user = request.user
    
    # 1. Buscamos as QuerySets base de cada nível de convite
    level_a_base = CustomUser.objects.filter(invited_by=user)
    level_b_base = CustomUser.objects.filter(invited_by__in=level_a_base)
    level_c_base = CustomUser.objects.filter(invited_by__in=level_b_base)

    # 2. Criamos uma função interna utilitária para mapear os membros e injetar o plano ativo real deles
    def injetar_plano_ativo(queryset):
        # Usamos prefetch_related para carregar os níveis ativos evitando centenas de consultas ao banco (Problema N+1)
        membros = queryset.order_by('-date_joined').prefetch_related('userlevel_set__level')
        
        for membro in membros:
            # Busca o primeiro UserLevel ativo deste afiliado
            plano_ativo = membro.userlevel_set.filter(is_active=True).first()
            
            if plano_ativo and plano_ativo.level:
                membro.level_active = True
                membro.nome_do_plano_activo = plano_ativo.level.name  # Ex: "VIP 1", "VIP 2", etc.
            else:
                membro.level_active = False
                membro.nome_do_plano_activo = "ESTAGIÁRIO"
                
        return membros

    # 3. Processamos os membros de todos os 3 níveis com seus planos reais injetados
    level_a_members = injetar_plano_ativo(level_a_base)
    level_b_members = injetar_plano_ativo(level_b_base)
    level_c_members = injetar_plano_ativo(level_c_base)

    context = {
        'level_a_members': level_a_members,
        'level_b_members': level_b_members,
        'level_c_members': level_c_members,
        'team_count': level_a_base.count() + level_b_base.count() + level_c_base.count(),
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={user.invite_code}',
        'subsidy_balance': user.subsidy_balance,
        'level_a_count': level_a_base.count(),
        'level_a_investors': level_a_base.filter(userlevel__is_active=True).distinct().count(),
        'level_b_count': level_b_base.count(),
        'level_c_count': level_c_base.count(),
    }
    return render(request, 'equipa.html', context)
# --- ROLETA ---
@login_required
def roleta(request):
    user = request.user
    roulette_settings = RouletteSettings.objects.first()
    prizes_list = [p.strip() for p in roulette_settings.prizes.split(',')] if roulette_settings and roulette_settings.prizes else ['0', '500', '1000', '0', '5000', '200', '0', '10000']
    recent_winners = Roulette.objects.filter(is_approved=True).order_by('-spin_date')[:10]
    context = {'roulette_spins': user.roulette_spins, 'prizes_list': prizes_list, 'recent_winners': recent_winners}
    return render(request, 'roleta.html', context)

@login_required
@require_POST
def spin_roulette(request):
    user = request.user
    if not user.roulette_spins or user.roulette_spins <= 0:
        return JsonResponse({'success': False, 'message': 'Sem giros.'})

    roulette_settings = RouletteSettings.objects.first()
    prizes_raw = [p.strip() for p in roulette_settings.prizes.split(',')] if roulette_settings and roulette_settings.prizes else ['0', '500', '1000', '0', '5000', '200', '0', '10000']
    weighted_pool = []
    for p in prizes_raw:
        val = Decimal(p)
        if val == 0: weighted_pool.extend([p] * 10)
        elif val <= 500: weighted_pool.extend([p] * 5)
        else: weighted_pool.append(p)

    winning_prize_str = random.choice(weighted_pool)
    prize_amount = Decimal(winning_prize_str)
    user.roulette_spins -= 1
    user.subsidy_balance += prize_amount
    user.available_balance += prize_amount
    user.save()
    Roulette.objects.create(user=user, prize=prize_amount, is_approved=True)

    return JsonResponse({'success': True, 'prize': winning_prize_str, 'remaining_spins': user.roulette_spins})

@login_required
def sobre(request):
    platform_settings = PlatformSettings.objects.first()
    history_text = platform_settings.history_text if platform_settings else 'Informação indisponível.'
    return render(request, 'sobre.html', {'history_text': history_text})

@login_required
def perfil(request):
    user = request.user
    bank_details, _ = BankDetails.objects.get_or_create(user=user)
    withdrawal_records = Withdrawal.objects.filter(user=user).order_by('-created_at')
    
    # --- CÁLCULO DOS INDICADORES DE CONTABILIDADE (ZONA LUANDA) ---
    luanda_tz = pytz.timezone('Africa/Luanda')
    now_luanda = timezone.now().astimezone(luanda_tz)
    today_luanda = now_luanda.date()
    
    # 1. Renda desta Semana (Tarefas concluídas nos últimos 7 dias)
    start_of_week = today_luanda - timezone.timedelta(days=today_luanda.weekday())
    semana_income = Task.objects.filter(
        user=user, 
        completed_at__date__gte=start_of_week
    ).aggregate(Sum('earnings'))['earnings__sum'] or Decimal('0.00')

    # 2. Renda deste Mês
    mes_atual_income = Task.objects.filter(
        user=user, 
        completed_at__date__year=today_luanda.year,
        completed_at__date__month=today_luanda.month
    ).aggregate(Sum('earnings'))['earnings__sum'] or Decimal('0.00')

    # 3. Renda do Mês Passado
    first_of_this_month = today_luanda.replace(day=1)
    last_day_of_last_month = first_of_this_month - timezone.timedelta(days=1)
    mes_passado_income = Task.objects.filter(
        user=user,
        completed_at__date__year=last_day_of_last_month.year,
        completed_at__date__month=last_day_of_last_month.month
    ).aggregate(Sum('earnings'))['earnings__sum'] or Decimal('0.00')

    # 4. Subsídio de Convite (Vem do saldo acumulado de subsídios do usuário)
    sub_convite = user.subsidy_balance

    # 5. Subsídio de Tarefa (Total histórico ganho em tarefas executadas)
    sub_tarefa = Task.objects.filter(user=user).aggregate(Sum('earnings'))['earnings__sum'] or Decimal('0.00')

    # 6. Total Sacado (Apenas saques com status 'Aprovado')
    total_sacado = Withdrawal.objects.filter(
        user=user, 
        status='Aprovado'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    # Obter o nível VIP ativo mais alto ou atual
    active_level = UserLevel.objects.filter(user=user, is_active=True).select_related('level').first()
    level_name = active_level.level.name if active_level else "Estagiário"

    if request.method == 'POST':
        if 'update_bank' in request.POST:
            form = BankDetailsForm(request.POST, instance=bank_details)
            if form.is_valid():
                form.save()
                messages.success(request, 'Banco atualizado com sucesso.')
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user_updated = password_form.save()
                update_session_auth_hash(request, user_updated)
                messages.success(request, 'Senha alterada com sucesso.')
        return redirect('perfil')
    
    context = {
        'user': user,
        'level_name': level_name,
        'form': BankDetailsForm(instance=bank_details),
        'password_form': PasswordChangeForm(request.user),
        'withdrawal_records': withdrawal_records,
        # Indicadores injetados no template
        'semana_income': semana_income,
        'mes_atual_income': mes_atual_income,
        'mes_passado_income': mes_passado_income,
        'sub_convite': sub_convite,
        'sub_tarefa': sub_tarefa,
        'total_sacado': total_sacado,
    }
    return render(request, 'perfil.html', context)

@login_required
def renda(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or 0
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or 0
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or 0
    total_income = (Task.objects.filter(user=user).aggregate(Sum('earnings'))['earnings__sum'] or 0) + user.subsidy_balance
    
    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'total_income': total_income,
    }
    return render(request, 'renda.html', context)
    