"""
Handler modules for the Telegram Wallet Generator bot.

This package contains all command and callback handlers organized by functionality.
"""

from .wallet_handlers import (
    cmd_generate,
    cmd_showseed, 
    cmd_delete,
    on_generate_callback,
    on_seed_callback,
    do_generate
)

from .bulk_handlers import (
    cmd_bulk,
    cmd_bulkzip,
    cmd_jobs,
    cmd_pause,
    cmd_resume, 
    cmd_cancel,
    on_bulk_operations_button,
    on_bulk_callback,
    on_bulk_count_input,
    on_generate_bulk_callback,
    on_job_callback
)

from .balance_handlers import (
    cmd_bal,
    cmd_mybal,
    on_balance_callback,
    on_check_balances_button,
    on_mybal_callback,
    on_mybal_mode_callback,
    on_mybal_single_nav,
    on_mybal_single_pick
)

from .ui_handlers import (
    cmd_start,
    cmd_help,
    cmd_menu,
    cmd_version,
    cmd_chains,
    on_quick_generate_button,
    on_view_chains_button,
    on_help_info_button,
    on_help_callback,
    on_my_wallets_button,
    on_wallet_callback,
    on_walletview_callback
)

from .profile_handlers import (
    cmd_my,
    cmd_mycsv,
    cmd_clearprofile
)

__all__ = [
    # Wallet handlers
    'cmd_generate', 'cmd_showseed', 'cmd_delete', 'on_generate_callback', 
    'on_seed_callback', 'do_generate',
    
    # Bulk handlers  
    'cmd_bulk', 'cmd_bulkzip', 'cmd_jobs', 'cmd_pause', 'cmd_resume', 'cmd_cancel',
    'on_bulk_operations_button', 'on_bulk_callback', 'on_bulk_count_input', 
    'on_generate_bulk_callback', 'on_job_callback',
    
    # Balance handlers
    'cmd_bal', 'cmd_mybal', 'on_balance_callback', 'on_check_balances_button',
    'on_mybal_callback', 'on_mybal_mode_callback', 'on_mybal_single_nav', 
    'on_mybal_single_pick',
    
    # UI handlers
    'cmd_start', 'cmd_help', 'cmd_menu', 'cmd_version', 'cmd_chains',
    'on_quick_generate_button', 'on_view_chains_button', 'on_help_info_button',
    'on_help_callback', 'on_my_wallets_button', 'on_wallet_callback', 
    'on_walletview_callback',
    
    # Profile handlers
    'cmd_my', 'cmd_mycsv', 'cmd_clearprofile'
]