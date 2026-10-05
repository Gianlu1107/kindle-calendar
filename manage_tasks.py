#!/usr/bin/env python3
"""
Kindle Calendar - Gestione Compiti delle Vacanze su PostgreSQL
Permette di visualizzare, aggiungere, aggiornare lo stato e rimuovere i compiti
delle vacanze direttamente dal database.

Uso:
  python manage_tasks.py list [holiday_type]
  python manage_tasks.py set-status <id> "<nuovo_stato>" [--progress <percentuale>]
  python manage_tasks.py add --holiday <type> --subject "<materia>" --desc "<descrizione>" --status "<stato>" [--is-test] [--progress <0-100>]
  python manage_tasks.py seed [--force]
"""

import sys
import argparse
from db import (
    get_holiday_tasks_db, update_task_status, add_holiday_task,
    init_db, seed_from_json, get_connection
)

def cmd_list(args):
    types = [args.holiday] if args.holiday else ["summer", "winter", "carnival", "easter"]
    for ht in types:
        print(f"\n=== COMPITI VACANZE: {ht.upper()} ===")
        tasks = get_holiday_tasks_db(ht)
        if tasks is None:
            print("  [!] Errore di connessione a PostgreSQL.")
            return
        if not tasks:
            print("  (nessun compito registrato)")
            continue
        for t in tasks:
            prog_str = f" [{t['progress_percent']}%]" if t.get("progress_percent") is not None else ""
            test_tag = " [VERIFICA]" if t.get("is_test") else ""
            print(f"  [{t['id']:02d}] {t['materia']}{test_tag}: {t['descrizione']}")
            print(f"       -> STATO: {t['stato']}{prog_str}")

def cmd_set_status(args):
    ok = update_task_status(args.id, args.status, progress_percent=args.progress)
    if ok:
        print(f"[+] Compito ID {args.id} aggiornato con successo a '{args.status}' (progress: {args.progress}%)")
    else:
        print(f"[-] Impossibile aggiornare il compito ID {args.id}")
        sys.exit(1)

def cmd_add(args):
    task_id = add_holiday_task(
        holiday_type=args.holiday,
        subject=args.subject,
        description=args.desc,
        status=args.status,
        progress_percent=args.progress,
        is_test=args.is_test
    )
    if task_id:
        print(f"[+] Nuovo compito aggiunto con successo (ID: {task_id}) a '{args.holiday}'")
    else:
        print("[-] Errore inserimento compito nel database")
        sys.exit(1)

def cmd_seed(args):
    init_db()
    ok = seed_from_json(force=args.force)
    if ok:
        print(f"[+] Seeding da file JSON a PostgreSQL completato con successo (force={args.force})")
    else:
        print("[-] Errore durante il seeding")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Kindle Calendar - Gestione Compiti Vacanze in PostgreSQL")
    subparsers = parser.add_subparsers(dest="command")

    # list
    p_list = subparsers.add_parser("list", help="Elenca compiti vacanze")
    p_list.add_argument("holiday", nargs="?", choices=["summer", "winter", "carnival", "easter"], help="Tipo vacanza")

    # set-status
    p_set = subparsers.add_parser("set-status", help="Aggiorna stato compito")
    p_set.add_argument("id", type=int, help="ID compito")
    p_set.add_argument("status", type=str, help="Nuova etichetta di stato (es. 'COMPLETATO', 'IN CORSO • 75%')")
    p_set.add_argument("--progress", type=int, default=None, help="Percentuale di completamento (opzionale, 0-100)")

    # add
    p_add = subparsers.add_parser("add", help="Aggiunge nuovo compito")
    p_add.add_argument("--holiday", required=True, choices=["summer", "winter", "carnival", "easter"], help="Tipo vacanza")
    p_add.add_argument("--subject", required=True, help="Materia")
    p_add.add_argument("--desc", required=True, help="Descrizione compito")
    p_add.add_argument("--status", required=True, help="Stato iniziale")
    p_add.add_argument("--progress", type=int, default=None, help="Percentuale")
    p_add.add_argument("--is-test", action="store_true", help="Contrassegna come verifica")

    # seed
    p_seed = subparsers.add_parser("seed", help="Inizializza e popola il database dai JSON")
    p_seed.add_argument("--force", action="store_true", help="Sovrascrive tabelle esistenti")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "set-status":
        cmd_set_status(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "seed":
        cmd_seed(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
