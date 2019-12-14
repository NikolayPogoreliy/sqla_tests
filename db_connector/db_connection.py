import logging
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from scrapy.utils.project import get_project_settings
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import Insert


@compiles(Insert)
def update_on_duplicate(insert, compiler, **kw):
    s = compiler.visit_insert(insert, **kw)
    if insert.kwargs.get('mysql_update_on_duplicate'):
        fields = s[s.find("(") + 1:s.find(")")].replace(" ", "").split(",")
        generated_directive = ["{0}=VALUES({0})".format(field) for field in fields]
        return s + " ON DUPLICATE KEY UPDATE " + ",".join(generated_directive)
    return s


Insert.argument_for("mysql", "update_on_duplicate", None)

logger = logging.getLogger(__name__)


class DBConnection(object):
    POOL_RECYCLE_TIMEOUT = 900
    POOL_SIZE = 2

    def __init__(self):
        super(DBConnection, self).__init__()
        logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
        settings = get_project_settings()
        query_params = {}
        settings_keys = settings.keys()
        if "DB_CHARSET" in settings_keys:
            query_params["charset"] = settings.get("DB_CHARSET")
        url = URL(
            drivername=settings.get("DB_DRIVER", "mysql"),
            username=settings.get("DB_USERNAME"),
            password=settings.get("DB_PASSWORD"),
            host=settings.get("DB_HOST"),
            port=settings.get("DB_PORT"),
            database=settings.get("DB_DATABASE"),
            query=query_params
        )
        self.db_engine = create_engine(url, pool_pre_ping=True, pool_recycle=self.POOL_RECYCLE_TIMEOUT,
                                       pool_size=self.POOL_SIZE)
        self.db_session = Session(self.db_engine, autoflush=False)

    def get_or_create(self, mapper, mapping, do_commit=True):
        instance = None
        try:
            instance = self.db_session.query(mapper).filter_by(**mapping).first()
            if not instance:
                instance = mapper(**mapping)
                self.db_session.add(instance)
                if do_commit:
                    self.db_session.flush()
                    self.db_session.commit()
        except Exception as e:
            logger.critical("GET OR CREATE")
            logger.critical(e)
            self.db_session.rollback()
            instance = self.db_session.query(mapper).filter_by(**mapping).first()
        return instance

    def get_or_upsert(self, mapper, mapping, update_mapping=None, do_commit=True):
        instance = None
        try:
            instance = self.db_session.query(mapper).filter_by(**mapping).first()
            flag = False
            if not instance:
                mapping.update(update_mapping)
                instance = mapper(**mapping)
                self.db_session.add(instance)
                self.db_session.flush()

            elif update_mapping:
                for attr, value in update_mapping.items():
                    instance.__setattr__(attr, value)
                self.db_session.merge(instance)
                self.db_session.flush()

            if do_commit:
                self.db_session.commit()
        except Exception as e:
            logger.critical("GET OR UPSERT")
            logger.critical(e)
            logger.critical(self.db_session.dirty)
            self.db_session.rollback()
            instance = self.db_session.query(mapper).filter_by(**mapping).first()
        if not instance:
            logger.critical(mapping)

        return instance

    def bulk_upsert(self, mapper, mappings, chunk_size=None):
        """Update statements via core execute() method"""
        if not chunk_size:
            chunk_size = len(mappings)
        conn = self.db_engine.connect()
        for chunk in range(0, len(mappings), chunk_size):
            s = mapper.__table__.insert(mysql_update_on_duplicate=True)
            conn.execute(
                s,
                mappings[chunk: chunk + chunk_size],
            )