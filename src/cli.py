"""Command Line Interface for Substack to TradingView Sync."""

import argparse
import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAVE_RICH = True
    console = Console()
except ImportError:
    HAVE_RICH = False
    console = None

from src.config import Settings
from src.logger import setup_logger
from src.models import DiffPlan
from src.clients.substack_client import SubstackClient, SubstackAuthError
from src.clients.google_sheets_client import GoogleSheetsClient, GoogleSheetsClientError
from src.clients.tradingview_client import (
    TradingViewClient,
    DryRunTradingViewBridge,
    TradingViewAuthError,
    TradingViewBridge,
)
from src.reconciliation import ReconciliationEngine


def _print(msg: str = "") -> None:
    """Helper for console printing across rich / standard stdout."""
    if HAVE_RICH and console:
        console.print(msg)
    else:
        # Strip simple rich tags if standard print
        clean = msg.replace("[bold green]", "").replace("[/bold green]", "")
        clean = clean.replace("[bold red]", "").replace("[/bold red]", "")
        clean = clean.replace("[bold cyan]", "").replace("[/bold cyan]", "")
        clean = clean.replace("[bold yellow]", "").replace("[/bold yellow]", "")
        clean = clean.replace("[bold]", "").replace("[/bold]", "")
        clean = clean.replace("[cyan]", "").replace("[/cyan]", "")
        clean = clean.replace("[green]", "").replace("[/green]", "")
        clean = clean.replace("[red]", "").replace("[/red]", "")
        clean = clean.replace("[yellow]", "").replace("[/yellow]", "")
        clean = clean.replace("[magenta]", "").replace("[/magenta]", "")
        clean = clean.replace("[dim]", "").replace("[/dim]", "")
        print(clean)


def print_diff_report(diff: DiffPlan) -> None:
    """Prints formatted summary tables of the reconciliation diff."""
    _print("\n[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    _print("[bold cyan]               SYNC RECONCILIATION REPORT                      [/bold cyan]")
    _print("[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]\n")

    # 1. Grants Table
    if diff.grants:
        if HAVE_RICH and console:
            table_grants = Table(title="🟢 Pending Grants (Access to Activate)", style="green")
            table_grants.add_column("Substack Email", style="white")
            table_grants.add_column("TradingView Handle", style="bold green")
            table_grants.add_column("Reason", style="dim")
            for g in diff.grants:
                table_grants.add_row(g.email or "-", g.tradingview_username, g.reason)
            console.print(table_grants)
        else:
            print("🟢 Pending Grants:")
            for g in diff.grants:
                print(f"  + Grant {g.tradingview_username} ({g.email}) - {g.reason}")
        _print()
    else:
        _print("[green]✔ No new grants pending.[/green]\n")

    # 2. Revokes Table
    if diff.revokes:
        if HAVE_RICH and console:
            table_revokes = Table(title="🔴 Pending Revocations (Access to Remove)", style="red")
            table_revokes.add_column("TradingView Handle", style="bold red")
            table_revokes.add_column("Reason", style="dim")
            for r in diff.revokes:
                table_revokes.add_row(r.tradingview_username, r.reason)
            console.print(table_revokes)
        else:
            print("🔴 Pending Revocations:")
            for r in diff.revokes:
                print(f"  - Revoke {r.tradingview_username} - {r.reason}")
        _print()
    else:
        _print("[green]✔ No revocations pending.[/green]\n")

    # 3. Unregistered Active Subscribers
    if diff.unregistered_paid_subscribers:
        if HAVE_RICH and console:
            table_unreg = Table(title="📋 Unregistered Paid Subscribers (Haven't Filled Form)", style="yellow")
            table_unreg.add_column("Substack Email", style="yellow")
            for email in diff.unregistered_paid_subscribers:
                table_unreg.add_row(email)
            console.print(table_unreg)
        else:
            print("📋 Unregistered Paid Subscribers:")
            for email in diff.unregistered_paid_subscribers:
                print(f"  ? {email}")
        _print()

    # 4. Unmatched Form Submissions
    if diff.unmatched_form_submissions:
        if HAVE_RICH and console:
            table_unmatched = Table(title="⚠️ Unmatched Form Submissions (No Active Paid Sub)", style="magenta")
            table_unmatched.add_column("Submitted Email", style="white")
            table_unmatched.add_column("Claimed TV Handle", style="magenta")
            table_unmatched.add_column("Submitted At", style="dim")
            for u in diff.unmatched_form_submissions:
                table_unmatched.add_row(u.email, u.tradingview_username, str(u.submitted_at))
            console.print(table_unmatched)
        else:
            print("⚠️ Unmatched Form Submissions:")
            for u in diff.unmatched_form_submissions:
                print(f"  ! {u.email} ({u.tradingview_username}) at {u.submitted_at}")
        _print()


def cmd_verify_auth(settings: Settings) -> int:
    """Verifies credentials and connections for all 3 services."""
    _print("[bold]Testing Connections to Substack, Google Sheets, and TradingView...[/bold]\n")
    logger = setup_logger()
    all_ok = True

    # 1. Test Substack
    try:
        substack = SubstackClient(settings.substack_subdomain, settings.substack_session_cookie, logger)
        substack.verify_connection()
        _print("[bold green]✔ Substack API:[/bold green] Connected to [cyan]" + settings.substack_subdomain + ".substack.com[/cyan]")
    except SubstackAuthError as e:
        _print(f"[bold red]✘ Substack API Error:[/bold red] {e}")
        all_ok = False
    except Exception as e:
        _print(f"[bold red]✘ Substack API Error:[/bold red] {e}")
        all_ok = False

    # 2. Test Google Sheets
    try:
        sheets = GoogleSheetsClient(settings.google_sheet_id, settings.google_sheet_name, logger)
        sheets.verify_connection()
        _print("[bold green]✔ Google Sheets API:[/bold green] Connected to Sheet ID [cyan]" + settings.google_sheet_id + "[/cyan]")
    except GoogleSheetsClientError as e:
        _print(f"[bold red]✘ Google Sheets Error:[/bold red] {e}")
        all_ok = False
    except Exception as e:
        _print(f"[bold red]✘ Google Sheets Error:[/bold red] {e}")
        all_ok = False

    # 3. Test TradingView
    try:
        tv = TradingViewClient(settings.tradingview_sessionid, settings.tradingview_sessionid_sign, logger)
        tv.verify_auth()
        _print("[bold green]✔ TradingView Bridge:[/bold green] Authenticated with script ID [cyan]" + settings.tradingview_script_id + "[/cyan]")
    except TradingViewAuthError as e:
        _print(f"[bold red]✘ TradingView Auth Error:[/bold red] {e}")
        all_ok = False
    except Exception as e:
        _print(f"[bold red]✘ TradingView Error:[/bold red] {e}")
        all_ok = False

    return 0 if all_ok else 1


def run_reconciliation(settings: Settings, bridge: TradingViewBridge) -> DiffPlan:
    """Executes live data fetching and diff calculation."""
    logger = setup_logger()
    _print("[bold green]Fetching data from Substack, Google Sheets, and TradingView...[/bold green]")
    substack = SubstackClient(settings.substack_subdomain, settings.substack_session_cookie, logger)
    subscribers = substack.fetch_all_subscribers()

    sheets = GoogleSheetsClient(settings.google_sheet_id, settings.google_sheet_name, logger)
    form_responses = sheets.fetch_form_responses()

    tv_users = bridge.get_authorized_users(settings.tradingview_script_id)

    engine = ReconciliationEngine(logger)
    return engine.calculate_diff(subscribers, form_responses, tv_users)


def cmd_diff(settings: Settings) -> int:
    """Calculates and previews the proposed diff plan."""
    logger = setup_logger()
    settings.validate_for_sync()
    bridge = DryRunTradingViewBridge(logger=logger)
    diff = run_reconciliation(settings, bridge)
    print_diff_report(diff)
    return 0


def cmd_sync(settings: Settings, apply: bool) -> int:
    """Synchronizes permissions with TradingView."""
    logger = setup_logger()
    settings.validate_for_sync()

    if not apply:
        _print("[bold yellow]DRY-RUN MODE (Simulation)[/bold yellow]\nPass [bold]--apply[/bold] to write live changes to TradingView.\n")
        bridge = DryRunTradingViewBridge(logger=logger)
    else:
        _print("[bold red]LIVE EXECUTION MODE[/bold red]\nApplying verified grants and revokes to TradingView...\n")
        bridge = TradingViewClient(settings.tradingview_sessionid, settings.tradingview_sessionid_sign, logger)

    diff = run_reconciliation(settings, bridge)
    print_diff_report(diff)

    if not diff.has_changes:
        _print("[bold green]Everything is up to date! Zero changes required.[/bold green]\n")
        return 0

    if apply:
        # Apply Grants
        for grant in diff.grants:
            _print(f"Granting access to [bold green]{grant.tradingview_username}[/bold green]...")
            bridge.grant_access(settings.tradingview_script_id, grant.tradingview_username)

        # Apply Revokes
        for revoke in diff.revokes:
            _print(f"Revoking access from [bold red]{revoke.tradingview_username}[/bold red]...")
            bridge.revoke_access(settings.tradingview_script_id, revoke.tradingview_username)

        _print("\n[bold green]✔ Synchronization Complete![/bold green]\n")

    return 0


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Substack to TradingView Sync CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: verify-auth
    subparsers.add_parser("verify-auth", help="Verify connection to Substack, Google Sheets, and TradingView")

    # Command: diff
    subparsers.add_parser("diff", help="Preview proposed access changes without modifying TradingView")

    # Command: sync
    sync_parser = subparsers.add_parser("sync", help="Synchronize permissions with TradingView")
    sync_parser.add_argument("--apply", action="store_true", help="Apply live changes to TradingView (defaults to dry-run)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    settings = Settings.load_from_env()

    if args.command == "verify-auth":
        sys.exit(cmd_verify_auth(settings))
    elif args.command == "diff":
        sys.exit(cmd_diff(settings))
    elif args.command == "sync":
        sys.exit(cmd_sync(settings, apply=args.apply))


if __name__ == "__main__":
    main()
