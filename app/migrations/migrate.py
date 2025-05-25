 await db_service.get_current_version()
        
        logger.info(f"Current database version: {current_version}")
        
        for migration in MIGRATIONS:
            if migration.version > current_version:
                logger.info(f"Applying migration {migration.version}: {migration.name}")
                await db_service.apply_migration(
                    migration.version,
                    migration.name,
                    migration.up_sql
                )
        
        final_version = await db_service.get_current_version()
        logger.info(f"Migrations completed. Database version: {final_version}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

async def rollback_to_version(target_version: int):
    """Откатывает миграции до указанной версии"""
    try:
        db_service = await get_database_service()
        current_version = await db_service.get_current_version()
        
        if target_version >= current_version:
            logger.warning(f"Target version {target_version} >= current version {current_version}")
            return
        
        # Откатываем миграции в обратном порядке
        for migration in reversed(MIGRATIONS):
            if migration.version > target_version and migration.version <= current_version:
                logger.info(f"Rolling back migration {migration.version}: {migration.name}")
                await db_service.rollback_migration(
                    migration.version,
                    migration.name,
                    migration.down_sql
                )
        
        final_version = await db_service.get_current_version()
        logger.info(f"Rollback completed. Database version: {final_version}")
        
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise

if __name__ == "__main__":
    import asyncio
    
    async def main():
        """CLI для управления миграциями"""
        import sys
        
        if len(sys.argv) < 2:
            print("Usage: python -m app.migrations.migrate [up|down|status]")
            sys.exit(1)
        
        command = sys.argv[1]
        
        if command == "up":
            await run_migrations()
        elif command == "down":
            if len(sys.argv) < 3:
                print("Usage: python -m app.migrations.migrate down <version>")
                sys.exit(1)
            target_version = int(sys.argv[2])
            await rollback_to_version(target_version)
        elif command == "status":
            db_service = await get_database_service()
            current_version = await db_service.get_current_version()
            print(f"Current database version: {current_version}")
            print(f"Available migrations: {len(MIGRATIONS)}")
            for migration in MIGRATIONS:
                status = "✓" if migration.version <= current_version else "✗"
                print(f"  {status} {migration.version}: {migration.name}")
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    
    asyncio.run(main())
