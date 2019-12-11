"""This series of tests illustrates different ways to UPDATE a large number
of rows in bulk.


"""
from sqlalchemy import Column, text
from sqlalchemy import create_engine
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from performance import Profiler


Base = declarative_base()
engine = None


class Customer(Base):
    __tablename__ = "customer"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    description = Column(String(255))


Profiler.init("bulk_updates", num=100000)


@Profiler.setup
def setup_database(dburl, echo, num):
    global engine
    engine = create_engine(dburl, echo=echo)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    s = Session(engine)
    for chunk in range(0, num, 10000):
        s.bulk_insert_mappings(
            Customer,
            [
                {
                    'id': i+1,
                    "name": "customer name %d" % i,
                    "description": "customer description %d" % i,
                }
                for i in range(chunk, chunk + 10000)
            ],
        )
    s.commit()


@Profiler.profile
def test_orm_flush(n):
    """UPDATE statements via the ORM flush process."""
    session = Session(bind=engine)
    for chunk in range(0, n, 1000):
        customers = (
            session.query(Customer)
            .filter(Customer.id.between(chunk, chunk + 1000))
            .all()
        )
        for customer in customers:
            customer.description = "updated"
        session.flush()
    session.commit()
    # print(len(session.query(Customer).all()))
    # print(len(session.query(Customer).filter(Customer.description == "updated").all()))


@Profiler.profile
def test_orm_bulk_update_mappings(n):
    '''Update statements via orm bulk_update_mappings() method'''
    session = Session(bind=engine)
    for chunk in range(0, n, 1000):
        session.bulk_update_mappings(
            Customer,
            [
                {
                    'id': i+1,
                    "name": "customer name %d" % i,
                    "description": "updated",
                }
                for i in range(chunk, chunk + 1000)
            ],
        )
        session.flush()
    session.commit()
    # print(len(session.query(Customer).all()))
    # print(len(session.query(Customer).filter(Customer.description=="updated").all()))

# @Profiler.profile
# def test_orm_bulk_save_objects(n):
#     '''Update statements via orm bulk_save_objects() method'''
#     session = Session(bind=engine)
#     for chunk in range(0, n, 1000):
#         session.bulk_save_objects(
#             [
#                 Customer(**{
#                     "name": "customer name %d" % i,
#                     "description": "updated",
#                 })
#                 for i in range(chunk, chunk + 1000)
#             ]
#         )
#         session.flush()
#     session.commit()

@Profiler.profile
def test_orm_update(n):
    '''Update statements via orm update() method'''
    session = Session(bind=engine)
    for chunk in range(0, n, 1000):
        customers = (
            session.query(Customer)
            .filter(Customer.id.between(chunk, chunk + 1000))
            .update(
                {Customer.description: 'updated'},
                synchronize_session=False
            )
        )
        session.flush()
    session.commit()
    # print(len(session.query(Customer).all()))
    # print(len(session.query(Customer).filter(Customer.description == "updated").all()))

@Profiler.profile
def test_core_update(n):
    """A single Core UPDATE construct inserting mappings in bulk."""
    conn = engine.connect()
    s = Customer.__table__.update()
    conn.execute(
        s,
        [
            dict(
                description="updated",
            )
            for i in range(n)
        ],
    )
    # conn.commit()

@Profiler.profile
def test_core_update_or_create(n):
    '''Update statements via core execute() method'''
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.sql.expression import Insert

    @compiles(Insert)
    def append_string(insert, compiler, **kw):
        s = compiler.visit_insert(insert, **kw)
        if insert.kwargs.get('mysql_append_string'):
            fields = s[s.find("(") + 1:s.find(")")].replace(" ", "").split(",")
            generated_directive = ["{0}=VALUES({0})".format(field) for field in fields]
            return s + " ON DUPLICATE KEY UPDATE " + ",".join(generated_directive)
        return s

    Insert.argument_for("mysql", "append_string", None)
    session = engine.connect()#Session(bind=engine)
    for chunk in range(0, n, 1000):
        s = Customer.__table__.insert(mysql_append_string=True)
        session.execute(
            s,
            [
                dict(
                    name="customer name %d" % i,
                    description="updated",
                )
                for i in range(chunk, chunk+1000)
            ],
        )
    # session.commit()


if __name__ == "__main__":
    Profiler.main()
