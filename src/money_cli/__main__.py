"""Ponto de entrada: `kotsu` (ou `money`, ou `python -m money_cli`)."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from money_cli import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kotsu", description="Finanças pessoais no terminal.")
    parser.add_argument("--dados", type=Path, help="pasta de dados (padrão: pasta do usuário)")
    parser.add_argument(
        "--pasta-dados",
        type=Path,
        metavar="PASTA",
        help="guarda PASTA (ex.: no Google Drive) como pasta de dados deste computador e sai",
    )
    parser.add_argument(
        "--pasta-dados-padrao",
        action="store_true",
        help="volta à pasta de dados padrão deste computador e sai",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="abre mesmo com o Kotsu aberto em outro computador ou com cópias em conflito",
    )
    troca = parser.add_mutually_exclusive_group()
    troca.add_argument(
        "--exportar",
        type=Path,
        metavar="ARQUIVO",
        help="escreve os dados num arquivo de troca para outro aparelho e sai",
    )
    troca.add_argument(
        "--importar",
        type=Path,
        metavar="ARQUIVO",
        help="junta aos dados daqui o arquivo de troca de outro aparelho e sai",
    )
    troca.add_argument(
        "--conferir",
        type=Path,
        nargs="?",
        const=True,
        metavar="ARQUIVO",
        help="mostra o código de conferência; com ARQUIVO, as diferenças para ele, e sai",
    )
    parser.add_argument("--version", action="version", version=f"money-cli {__version__}")
    args = parser.parse_args(argv)

    if args.pasta_dados is not None or args.pasta_dados_padrao:
        return _configurar_pasta(args)

    from money_cli.armazenamento import trava
    from money_cli.armazenamento.banco import Banco
    from money_cli.armazenamento.caminhos import arquivo_do_banco, pasta_de_backups
    from money_cli.tela.app import MoneyApp

    arquivo = arquivo_do_banco(args.dados)
    pasta = arquivo.parent
    copias = trava.conflitos(pasta, arquivo.name)
    if copias and not args.forcar:
        lista = "\n".join(f"  {c}" for c in copias)
        print(
            "O Drive guardou cópias do banco em conflito (dois computadores salvaram ao mesmo\n"
            f"tempo):\n{lista}\n"
            "Veja qual tem os lançamentos certos, deixe só ele como money.sqlite e mova as\n"
            "outras para fora da pasta. Para abrir mesmo assim: kotsu --forcar",
            file=sys.stderr,
        )
        return 1
    try:
        minha = trava.tomar(pasta, f"{dt.datetime.now():%d/%m/%Y %H:%M}", args.forcar)
    except trava.BancoEmUso as erro:
        print(
            f"{erro}\nFeche o Kotsu lá e espere o Drive terminar de sincronizar. Se ele foi\n"
            "fechado à força, use: kotsu --forcar",
            file=sys.stderr,
        )
        return 1
    try:
        banco = Banco.abrir(arquivo, pasta_de_backups(pasta))
        try:
            if args.exportar or args.importar or args.conferir:
                return _trocar(banco, args)
            MoneyApp(banco, pasta_tema=pasta).run()
        finally:
            banco.fechar()
    finally:
        minha.liberar()
    return 0


def _trocar(banco, args: argparse.Namespace) -> int:
    """`--exportar`, `--importar` e `--conferir` (D39): troca de dados entre aparelhos."""
    from money_cli.armazenamento import troca
    from money_cli.dominio import mescla

    try:
        if args.exportar:
            codigo = troca.exportar(banco, args.exportar.expanduser())
            print(f"Dados exportados para {args.exportar}\nCódigo de conferência: {codigo}")
        elif args.importar:
            resumo = troca.importar(banco, args.importar.expanduser())
            if resumo.nada:
                print("Nada mudou aqui: este aparelho já tinha tudo o que o arquivo traz.")
            else:
                print(
                    f"Lançamentos: {resumo.entraram} entraram, {resumo.mudaram} mudaram,"
                    f" {resumo.sairam} saíram."
                )
            print(f"Código de conferência: {troca.codigo(banco)}")
            diferencas = troca.comparar(banco, args.importar.expanduser())
            if not diferencas.iguais:
                print(
                    "O outro aparelho ainda não tem tudo o que há aqui: exporte daqui e"
                    " importe lá para os códigos baterem."
                )
        elif args.conferir is True:
            print(f"Código de conferência: {troca.codigo(banco)}")
        else:
            aqui = troca.ler_estado(banco)
            la = troca.ler_arquivo(args.conferir.expanduser())
            diferencas = mescla.comparar(aqui, la)
            print(f"Código daqui:      {diferencas.codigo_aqui}")
            print(f"Código do arquivo: {diferencas.codigo_la}")
            if diferencas.iguais:
                print("Iguais: os dois têm os mesmos dados.")
                return 0
            for titulo, itens, estado in (
                ("Só aqui", diferencas.so_aqui, aqui),
                ("Só no arquivo", diferencas.so_la, la),
            ):
                if itens:
                    print(f"\n{titulo} ({len(itens)}):")
                    for item in itens:
                        print(f"  {mescla.descrever(item, estado)}")
            if diferencas.diferentes:
                print(f"\nDiferentes ({len(diferencas.diferentes)}):")
                for meu, dele in diferencas.diferentes:
                    print(f"  aqui:    {mescla.descrever(meu, aqui)}")
                    print(f"  arquivo: {mescla.descrever(dele, la)}")
            if not (diferencas.so_aqui or diferencas.so_la or diferencas.diferentes):
                print("Os lançamentos são os mesmos; a diferença está em contas, categorias,")
                print("séries de todo mês ou exclusões ainda não trocadas.")
            return 2
    except mescla.ErroDeTroca as erro:
        print(f"Não deu certo: {erro}", file=sys.stderr)
        return 1
    except OSError as erro:
        print(f"Não foi possível gravar o arquivo: {erro}", file=sys.stderr)
        return 1
    return 0


def _configurar_pasta(args: argparse.Namespace) -> int:
    """`--pasta-dados`: aponta este computador para uma pasta (ex.: do Drive) e sai."""
    from money_cli.armazenamento import caminhos
    from money_cli.armazenamento.banco import copiar_arquivo_banco

    try:
        if args.pasta_dados_padrao:
            caminhos.gravar_pasta_configurada(None)
            print(f"Pasta de dados: {caminhos.pasta_local()} (padrão).")
            return 0
        destino = args.pasta_dados.expanduser().resolve()
        novo = caminhos.arquivo_do_banco(destino)
        atual = caminhos.arquivo_do_banco(caminhos.pasta_de_dados())
        if atual.resolve() != novo and atual.exists():
            if novo.exists():
                print(
                    f"Já existe um banco em {novo} e outro em {atual}. O Kotsu não junta os\n"
                    "dois: escolha qual vale, mova o outro para fora e rode de novo.",
                    file=sys.stderr,
                )
                return 1
            destino.mkdir(parents=True, exist_ok=True)
            copiar_arquivo_banco(atual, novo)
            print(f"Banco copiado para {novo} (o original continua em {atual}).")
        caminhos.gravar_pasta_configurada(destino)
    except OSError as erro:
        print(f"Não foi possível configurar a pasta: {erro}", file=sys.stderr)
        return 1
    print(
        f"Pasta de dados deste computador: {destino}\nBackups (tecla b) ficam em "
        f"{caminhos.pasta_local() / 'backups'}, fora da sincronização."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
