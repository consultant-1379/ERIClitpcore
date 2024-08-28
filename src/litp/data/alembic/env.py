# pylint: disable=W0611,E1101,C0103,C0111
from __future__ import with_statement
from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig

from litp.data.types import Base

import os
import cherrypy
# All this imports are required because models do not inherit
# declarative_base() directly.
# All these modules contain classes multiple inheriting both model and base.
# When a new model is added it must be imported here as well!
import litp.core.persisted_task
import litp.core.extension_info
import litp.core.plan
import litp.core.plugin_info
import litp.core.plan_task
import litp.core.model_item
import litp.core.task
from litp.data.global_options import GlobalOption

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.attributes.get('init_logging', True):
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = config.attributes.get('connection', None)

    if connectable is None:
        # only create Engine if we don't have a Connection
        # from the outside
        config_path = os.getenv('CONFIG_PATH')
        if config_path is None:
            raise RuntimeError(
                'Environment variable CONFIG_PATH must point to litpd.conf.')
        cherrypy.config.update(config_path)
        # suppress cherrypy's internal logging config for non-service use.
        cherrypy.config.update({'log.screen': False,
                            'log.access_file': '',
                            'log.error_file': ''})
        cherrypy.engine.unsubscribe('graceful', cherrypy.log.reopen_files)
        connectable = engine_from_config(
            dict(cherrypy.config.items()),
            prefix='sqlalchemy.',
            poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        dialect_name="postgresql",  # specify dialect directly
        target_metadata=target_metadata,
        literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
