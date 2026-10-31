import json
from pathlib import Path

import typer

from alysia.social.service import Proposal, SocialService

app=typer.Typer(help="莉娅每日21:00—21:30的公开互动策略、去重与发送记录。",no_args_is_help=True)


def service() -> SocialService:
    return SocialService(Path(__file__).resolve().parents[2])


def output(value: dict) -> None:
    typer.echo(json.dumps(value,ensure_ascii=False,indent=2))


@app.command()
def status() -> None:
    output(service().status())


@app.command()
def instructions() -> None:
    output(service().instructions())


@app.command()
def reserve(proposal: Path) -> None:
    try:
        output(service().reserve(Proposal.model_validate_json(proposal.read_text(encoding="utf-8-sig"))))
    except ValueError as error:
        typer.echo(str(error),err=True)
        raise typer.Exit(2)


@app.command()
def receipt(reservation_id: str, state: str, evidence: str=typer.Option(...), remote_url: str|None=typer.Option(None)) -> None:
    try:
        output(service().receipt(reservation_id,state,evidence=evidence,remote_url=remote_url))
    except ValueError as error:
        typer.echo(str(error),err=True)
        raise typer.Exit(2)
