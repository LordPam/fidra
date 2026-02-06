#!/usr/bin/env python
"""Utility script to clean up PLANNED transactions in the database.

This script finds any transactions with PLANNED status and either:
1. Converts them to PENDING (for expenses) or AUTO (for income)
2. Or deletes them if you prefer

Run this script if you have old PLANNED transactions causing errors.

Usage:
    python cleanup_planned_transactions.py [--delete]

Options:
    --delete    Delete PLANNED transactions instead of converting them
"""

import asyncio
import sys
from pathlib import Path

from fidra.app import ApplicationContext
from fidra.domain.models import ApprovalStatus, TransactionType


async def cleanup_planned_transactions(delete_mode: bool = False):
    """Clean up PLANNED transactions in database.

    Args:
        delete_mode: If True, delete PLANNED transactions. If False, convert them.
    """
    # Initialize context
    ctx = ApplicationContext(db_path=Path("fidra.db"))
    await ctx.initialize()

    try:
        # Load all transactions
        all_transactions = await ctx.transaction_repo.get_all()

        # Find PLANNED transactions
        planned_transactions = [t for t in all_transactions if t.status == ApprovalStatus.PLANNED]

        if not planned_transactions:
            print("✓ No PLANNED transactions found in database. Everything is clean!")
            return

        print(f"Found {len(planned_transactions)} PLANNED transaction(s):")
        for t in planned_transactions:
            print(f"  - {t.date} | {t.description} | £{t.amount} | {t.type.value}")

        if delete_mode:
            # Delete mode
            print("\n⚠️  DELETE MODE: These transactions will be permanently deleted.")
            response = input("Continue? (yes/no): ")

            if response.lower() != "yes":
                print("Cancelled.")
                return

            for t in planned_transactions:
                await ctx.transaction_repo.delete(t.id)
                print(f"  ✓ Deleted: {t.description}")

            print(f"\n✓ Successfully deleted {len(planned_transactions)} transaction(s).")

        else:
            # Convert mode
            print("\n📝 CONVERT MODE: These transactions will be converted to actual transactions.")
            print("   - Income → AUTO status")
            print("   - Expense → PENDING status")
            response = input("Continue? (yes/no): ")

            if response.lower() != "yes":
                print("Cancelled.")
                return

            for t in planned_transactions:
                # Determine new status
                if t.type == TransactionType.INCOME:
                    new_status = ApprovalStatus.AUTO
                else:
                    new_status = ApprovalStatus.PENDING

                # Update transaction
                updated = t.with_updates(status=new_status)
                await ctx.transaction_repo.save(updated)
                print(f"  ✓ Converted: {t.description} → {new_status.value}")

            print(f"\n✓ Successfully converted {len(planned_transactions)} transaction(s).")

    finally:
        await ctx.close()


def main():
    """Main entry point."""
    delete_mode = "--delete" in sys.argv

    print("=" * 60)
    print("Fidra Database Cleanup Utility")
    print("=" * 60)
    print()

    asyncio.run(cleanup_planned_transactions(delete_mode))


if __name__ == "__main__":
    main()
