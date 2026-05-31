"""
Flask CLI commands for database archiving.
"""

import click
from flask.cli import with_appcontext


@click.group()
def archive():
    """Move old data from main database to archive database."""
    pass


@archive.command('stats')
@with_appcontext
def archive_stats():
    """Show main vs archive record counts and eligible records."""
    from archive import get_archive_manager

    manager = get_archive_manager()
    if not manager:
        click.echo('Archive system not initialized.')
        return

    stats = manager.get_stats()
    click.echo('\n=== Database Archive Statistics ===\n')
    click.echo('MAIN DATABASE (operational):')
    for key, val in stats['main'].items():
        click.echo(f'  {key}: {val:,}')

    click.echo('\nARCHIVE DATABASE (historical):')
    for key, val in stats['archive'].items():
        click.echo(f'  {key}: {val:,}')

    click.echo('\nELIGIBLE FOR ARCHIVING NOW:')
    for key, val in stats['eligible_now'].items():
        click.echo(f'  {key}: {val:,}')

    click.echo('\nRETENTION POLICY (days):')
    for key, val in stats['retention_days'].items():
        click.echo(f'  {key}: {val}')


@archive.command('run')
@click.option('--dry-run', is_flag=True, help='Preview counts without moving data')
@with_appcontext
def archive_run(dry_run):
    """Run archive job — copy old records to archive DB and remove from main DB."""
    from archive import get_archive_manager

    manager = get_archive_manager()
    if not manager:
        click.echo('Archive system not initialized.')
        return

    if dry_run:
        click.echo('DRY RUN — no data will be modified.\n')

    result = manager.run(triggered_by='cli', dry_run=dry_run)

    if result['success']:
        click.echo('Archive completed successfully.\n')
        for key, val in result['summary'].items():
            if key != 'dry_run':
                click.echo(f'  {key}: {val:,}')
    else:
        click.echo(f"Archive FAILED: {result.get('error')}")


@archive.command('config')
@with_appcontext
def archive_config():
    """Show current archive retention configuration."""
    from archive import get_archive_manager

    manager = get_archive_manager()
    if not manager:
        click.echo('Archive system not initialized.')
        return

    import json
    click.echo(json.dumps(manager.config, indent=2))


def init_archive_cli(app):
    app.cli.add_command(archive)
