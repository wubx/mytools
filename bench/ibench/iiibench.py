#!/usr/bin/python -W ignore::DeprecationWarning
#
# Copyright (C) 2009 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implements a modified version of the insert benchmark as defined by Tokutek.

   A typical command line is:
     iibench.py --db_user=foo --db_password=bar --max_rows=1000000000

   Results are printed after each rows_per_reports rows are inserted.
   The output is:
     Legend:
       #rows = total number of rows inserted
       #seconds = number of seconds for the last insert batch
       #total_seconds = total number of seconds the test has run
       cum_ips = #rows / #total_seconds
       table_size = actual table size (inserts - deletes)
       last_ips = #rows / #seconds
       #queries = total number of queries
       cum_qps = #queries / #total_seconds
       last_ips = #queries / #seconds
       #rows #seconds cum_ips table_size last_ips #queries cum_qps last_qps
     1000000 895 1118 1000000 1118 5990 5990 7 7
     2000000 1897 1054 2000000 998 53488 47498 28 47

  The insert benchmark is defined at http://blogs.tokutek.com/tokuview/iibench

  This differs with the original by running queries concurrent with the inserts.
  For procesess are started and each is assigned one of the indexes. Each
  process then runs index-only queries in a loop that scan and fetch data
  from rows_per_query index entries.
"""

__author__ = 'Mark Callaghan'
__author__ = 'wubx'

import os
import base64
import string
from multiprocessing import Queue, Process, Pipe, Array, Lock
import optparse
from datetime import datetime
import time
import random
import sys
import math
import timeit

#
# flags module, on loan from gmt module by Chip Turner.
#

FLAGS = optparse.Values()
parser = optparse.OptionParser()

letters_and_digits = string.ascii_letters + string.digits


def DEFINE_string(name, default, description, short_name=None):
    if default is not None and default != '':
        description = "%s (default: %s)" % (description, default)
    args = ["--%s" % name]
    if short_name is not None:
        args.insert(0, "-%s" % short_name)

    parser.add_option(type="string", help=description, *args)
    parser.set_default(name, default)
    setattr(FLAGS, name, default)


def DEFINE_integer(name, default, description, short_name=None):
    if default is not None and default != '':
        description = "%s (default: %s)" % (description, default)
    args = ["--%s" % name]
    if short_name is not None:
        args.insert(0, "-%s" % short_name)

    parser.add_option(type="int", help=description, *args)
    parser.set_default(name, default)
    setattr(FLAGS, name, default)


def DEFINE_boolean(name, default, description, short_name=None):
    if default is not None and default != '':
        description = "%s (default: %s)" % (description, default)
    args = ["--%s" % name]
    if short_name is not None:
        args.insert(0, "-%s" % short_name)

    parser.add_option(action="store_true", help=description, *args)
    parser.set_default(name, default)
    setattr(FLAGS, name, default)


def ParseArgs(argv):
    usage = sys.modules["__main__"].__doc__
    parser.set_usage(usage)
    unused_flags, new_argv = parser.parse_args(args=argv, values=FLAGS)

    if FLAGS.dbms == 'mongo':
        globals()['pymongo'] = __import__('pymongo')
    elif FLAGS.dbms == 'mysql':
        globals()['MySQLdb'] = __import__('MySQLdb')
    elif FLAGS.dbms == 'mysqlx':
        globals()['mysqlx'] = __import__('mysqlx')
    elif FLAGS.dbms == 'postgres':
        globals()['psycopg2'] = __import__('psycopg2')
    else:
        print('dbms must be one of: mysql, mongodb, postgres')
        sys.exit(-1)

    return new_argv


def ShowUsage():
    parser.print_help()


#
# options
#

DEFINE_integer('data_length_max', 10, 'Max size of data in data column')
DEFINE_integer('data_length_min', 10, 'Min size of data in data column')
DEFINE_integer('data_random_pct', 50, 'Percentage of row that has random data')
DEFINE_integer('rows_per_commit', 1000, '#rows per transaction')
DEFINE_integer('rows_per_report', 1000000,
               '#rows per progress report printed to stdout. If this '
               'is too small, some rates may be negative.')
DEFINE_integer('rows_per_query', 10,
               'Number of rows per to fetch per query. Each query '
               'thread does one query per insert.')
DEFINE_integer('cashregisters', 1000, '# cash registers')
DEFINE_integer('products', 10000, '# products')
DEFINE_integer('customers', 100000, '# customers')
DEFINE_integer('max_price', 500, 'Maximum value for price column')
DEFINE_integer('max_rows', 10000, 'Number of rows to insert')
DEFINE_boolean('no_inserts', False, 'When True don''t do inserts')
DEFINE_integer('query_threads', 0, 'Number of query threads')
DEFINE_boolean('setup', False,
               'Create table. Drop and recreate if it exists.')
DEFINE_integer('warmup', 0, 'TODO')
DEFINE_integer('max_table_rows', 10000000, 'Maximum number of rows in table')
DEFINE_boolean('with_max_table_rows', False,
               'When True, allow table to grow to max_table_rows, then delete oldest')
DEFINE_integer('num_secondary_indexes', 3, 'Number of secondary indexes (0 to 3)')
DEFINE_boolean('secondary_at_end', False, 'Create secondary index at end')
DEFINE_integer('inserts_per_second', 0, 'Rate limit for inserts')
DEFINE_integer('seed', 3221223452, 'RNG seed')
# Can override other options, see get_conn
DEFINE_string('dbopt', 'none', 'Per DBMS options, comma separated')

DEFINE_string('dbms', 'mysql', 'one of: mysql, mysqlx, mongodb, postgres')

DEFINE_boolean('mysqlx_trx', False, 'Use mysqlx transactions when true')

# MySQL & MongoDB flags
DEFINE_string('db_host', 'localhost', 'Hostname for the test')
DEFINE_string('db_port', '33060', 'port for test')
DEFINE_string('db_name', 'test', 'Name of database for the test')
DEFINE_string('table_name', 'purchases_index', 'Name of table to use')

# MySQL flags
DEFINE_string('engine', 'innodb', 'Storage engine for the table')
DEFINE_string('engine_options', '', 'Options for create table')
DEFINE_string('db_user', 'root', 'DB user for the test')
DEFINE_string('db_password', '', 'DB password for the test')
DEFINE_string('db_config_file', '', 'MySQL configuration file')
DEFINE_string('db_socket', '/tmp/mysql.sock', 'socket for mysql connect')
DEFINE_integer('unique_checks', 1, 'Set unique_checks')
DEFINE_integer('bulk_load', 1, 'Enable bulk load optimizations - only RocksDB today')

# MongoDB flags
DEFINE_integer('mongo_w', 1, 'Value for MongoDB write concern: w')
DEFINE_boolean('mongo_j', False, 'Value for MongoDB write concern: j')
DEFINE_boolean('mongo_trx', False, 'Use Mongo transactions when true')
DEFINE_string('name_cash', 'cashregisterid', 'Name for cashregisterid attribute')
DEFINE_string('name_cust', 'customerid', 'Name for customerid attribute')
DEFINE_string('name_ts', 'dateandtime', 'Name for dateandtime attribute')
DEFINE_string('name_price', 'price', 'Name for price attribute')
DEFINE_string('name_prod', 'product', 'Name for product attribute')
DEFINE_string('name_data', 'data', 'Name for data attribute')

# ES

#
# iibench
#

insert_done = 'insert_done'


def rthist_new():
    obj = {}
    hist = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    obj['hist'] = hist
    obj['max'] = 0
    return obj


def rthist_start(obj):
    return timeit.default_timer()


def rthist_finish(obj, start):
    now = timeit.default_timer()
    elapsed = now - start
    # Linear search assuming the first few buckets get the most responses
    # And when not, then the overhead of this isn't relevant

    if elapsed >= obj['max']:
        obj['max'] = elapsed

    rt = obj['hist']

    if elapsed <= 0.000256:
        rt[0] += 1
    elif elapsed <= 0.001:
        rt[1] += 1
    elif elapsed <= 0.004:
        rt[2] += 1
    elif elapsed <= 0.016:
        rt[3] += 1
    elif elapsed <= 0.064:
        rt[4] += 1
    elif elapsed <= 0.256:
        rt[5] += 1
    elif elapsed <= 1:
        rt[6] += 1
    elif elapsed <= 4:
        rt[7] += 1
    elif elapsed <= 16:
        rt[8] += 1
    else:
        rt[9] += 1


def rthist_result(obj, prefix):
    rt = obj['hist']
    res = '%10s %9s %9s %9s %9s %9s %9s %9s %9s %9s %9s %11s\n' \
          '%10s %9d %9d %9d %9d %9d %9d %9d %9d %9d %9d %11.6f' % (
              prefix, '256us', '1ms', '4ms', '16ms', '64ms', '256ms', '1s', '4s', '16s', 'gt', 'max',
              prefix, rt[0], rt[1], rt[2], rt[3], rt[4], rt[5], rt[6], rt[7], rt[8], rt[9], obj['max'])
    return res


def get_conn():
    if FLAGS.dbms == 'mongo':

        if FLAGS.dbopt != 'none':
            mopts = FLAGS.dbopt.split(',')
            for mopt in mopts:
                if mopt == 'journal':
                    FLAGS.mongo_j = True
                elif mopt == 'transaction':
                    FLAGS.mongo_trx = True

        return pymongo.MongoClient("mongodb://%s:%s@%s:27017" % (FLAGS.db_user, FLAGS.db_password, FLAGS.db_host))
    elif FLAGS.dbms == 'mysql':
        return MySQLdb.connect(host=FLAGS.db_host, user=FLAGS.db_user,
                               db=FLAGS.db_name, passwd=FLAGS.db_password,
                               unix_socket=FLAGS.db_socket, read_default_file=FLAGS.db_config_file,
                               autocommit=True)
    elif FLAGS.dbms == 'mysqlx':
        return mysqlx.get_session({
            'host': FLAGS.db_host,
            'port': FLAGS.db_port,
            'user': FLAGS.db_user,
            'password': FLAGS.db_password
        })
    else:
        # TODO user, passwd, etc
        conn = psycopg2.connect(dbname=FLAGS.db_name, host=FLAGS.db_host)
        conn.set_session(autocommit=True)
        return conn


def create_index_mongo():
    conn = get_conn()
    db = conn[FLAGS.db_name]

    if FLAGS.num_secondary_indexes >= 1:
        db[FLAGS.table_name].create_index([(FLAGS.name_price, pymongo.ASCENDING),
                                           (FLAGS.name_cust, pymongo.ASCENDING)], name="pc")
    if FLAGS.num_secondary_indexes >= 2:
        db[FLAGS.table_name].create_index([(FLAGS.name_cash, pymongo.ASCENDING),
                                           (FLAGS.name_price, pymongo.ASCENDING),
                                           (FLAGS.name_cust, pymongo.ASCENDING)], name="cpc")
    if FLAGS.num_secondary_indexes >= 3:
        db[FLAGS.table_name].create_index([(FLAGS.name_price, pymongo.ASCENDING),
                                           (FLAGS.name_ts, pymongo.ASCENDING),
                                           (FLAGS.name_cust, pymongo.ASCENDING)], name="pdc")


def create_table_mongo():
    conn = get_conn()
    db = conn[FLAGS.db_name]
    db.drop_collection(FLAGS.table_name)


def create_index_mysqlx():
    if FLAGS.num_secondary_indexes >= 1:
        conn = get_conn()
        db = conn.get_schema(FLAGS.db_name)
        myCol =db.get_collection(FLAGS.table_name)
        # myC.createIndex("idx_1", {fields:[{field:'$.price', type:'float'},{field:'$.customerid', type:'INT'}]})
        myCol.create_index("idx_1", {"fields":[{"field":'$.price', "type":'float'},{"field":'$.customerid', "type":'INT'}]}).execute()

        if FLAGS.num_secondary_indexes >= 2:
            myCol.create_index("idx_2",
                              {"fields": [{"field": '$.cashregisterid', "type": 'int'},{"field": '$.price', "type": 'float'},
                                        {"field": '$.customerid', "type": 'INT'}]}).execute()

        if FLAGS.num_secondary_indexes >= 3:
            myCol.create_index("idx_3",
                              {"fields": [{"field": '$.price', "type": 'float'},
                                        {"field": '$.dateandtime', "type": 'datetime'},
                                        {"field": '$.customerid', "type": 'INT'}]}).execute()

        conn.close()

def create_table_mysqlx():
    conn = get_conn()
    db = conn.get_schema(FLAGS.db_name)
    db.drop_collection(FLAGS.table_name)
    db.create_collection(FLAGS.table_name)



def create_table_mysql():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('drop table if exists %s' % FLAGS.table_name)

    ddl_sql = 'transactionid bigint not null auto_increment, ' \
              'dateandtime datetime, ' \
              'cashregisterid int not null, ' \
              'customerid int not null, ' \
              'productid int not null, ' \
              'price float not null, ' \
              'data varchar(4000), ' \
              'primary key (transactionid) '

    ddl_sql = 'create table %s ( %s ) engine=%s %s' % (
        FLAGS.table_name, ddl_sql, FLAGS.engine, FLAGS.engine_options)
    print(ddl_sql)
    cursor.execute(ddl_sql)

    cursor.close()
    conn.close()


def create_index_postgres():
    if FLAGS.num_secondary_indexes >= 1:
        conn = get_conn()
        cursor = conn.cursor()

        # TODO: should fillfactor be set?
        ddl = "create index %s_marketsegment on %s (price, customerid) " % (
            FLAGS.table_name, FLAGS.table_name)
        cursor.execute(ddl)

        if FLAGS.num_secondary_indexes >= 2:
            ddl = "create index %s_registersegment on %s (cashregisterid, price, customerid) " % (
                FLAGS.table_name, FLAGS.table_name)
            cursor.execute(ddl)

        if FLAGS.num_secondary_indexes >= 3:
            ddl = "create index %s_pdc on %s (price, dateandtime, customerid) " % (
                FLAGS.table_name, FLAGS.table_name)
            cursor.execute(ddl)

        conn.commit()
        cursor.close()
        conn.close()


def create_table_postgres():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('drop table if exists %s' % FLAGS.table_name)

    ddl_sql = 'transactionid bigserial primary key, ' \
              'dateandtime timestamp without time zone, ' \
              'cashregisterid int not null, ' \
              'customerid int not null, ' \
              'productid int not null, ' \
              'price real not null, ' \
              'data varchar(4000) '

    ddl_sql = 'create table %s ( %s ) %s' % (
        FLAGS.table_name, ddl_sql, FLAGS.engine_options)
    print(ddl_sql)
    cursor.execute(ddl_sql)
    conn.commit()

    # TODO: what is a good value for cache to reduce overhead?
    ddl_sql = 'alter sequence %s_transactionid_seq cache 1000' % (FLAGS.table_name)
    print(ddl_sql)
    cursor.execute(ddl_sql)
    conn.commit()

    cursor.close()
    conn.close()


def create_table():
    if FLAGS.dbms == 'mongo':
        create_table_mongo()
    elif FLAGS.dbms == 'mysqlx':
        create_table_mysqlx()
    elif FLAGS.dbms == 'mysql':
        create_table_mysql()
    else:
        create_table_postgres()


def create_index():
    if FLAGS.dbms == 'mongo':
        create_index_mongo()
    elif FLAGS.dbms == 'mysqlx':
        create_index_mysqlx()
    elif FLAGS.dbms == 'mysql':
        create_index_mysql()
    else:
        create_index_postgres()


def generate_cols(rand_data_buf):
    cashregisterid = random.randrange(0, FLAGS.cashregisters)
    productid = random.randrange(0, FLAGS.products)
    customerid = random.randrange(0, FLAGS.customers)
    price = ((random.random() * FLAGS.max_price) + customerid) / 100.0
    data_len = random.randrange(FLAGS.data_length_min, FLAGS.data_length_max + 1)
    # multiply by 0.75 to account of base64 overhead
    rand_data_len = int(data_len * 0.75 * (float(FLAGS.data_random_pct) / 100))
    rand_data_off = random.randrange(0, len(rand_data_buf) - rand_data_len)
    nonrand_data_len = data_len - rand_data_len

    data = '%s%s' % ('a' * nonrand_data_len,
                     rand_data_buf[rand_data_off:(rand_data_off + rand_data_len)])
    return cashregisterid, productid, customerid, price, data


def generate_row_mongo(when, rand_data_buf):
    cashregisterid, productid, customerid, price, data = generate_cols(rand_data_buf)
    return {FLAGS.name_ts: when, FLAGS.name_cash: cashregisterid,
            FLAGS.name_cust: customerid, FLAGS.name_prod: productid,
            FLAGS.name_price: price, FLAGS.name_data: data}


def generate_row_mysqlx(when, rand_data_buf):
    cashregisterid, productid, customerid, price, data = generate_cols(rand_data_buf)
    return {FLAGS.name_ts: when, FLAGS.name_cash: cashregisterid,
            FLAGS.name_cust: customerid, FLAGS.name_prod: productid,
            FLAGS.name_price: price, FLAGS.name_data: data}


def generate_row_mysql_pg(when, rand_data_buf):
    cashregisterid, productid, customerid, price, data = generate_cols(rand_data_buf)
    return "('%s',%d,%d,%d,%.2f,'%s')" % (
        when, cashregisterid, customerid, productid, price, data)


def generate_row(when, rand_data_buf):
    if FLAGS.dbms == 'mongo':
        return generate_row_mongo(when, rand_data_buf)
    elif FLAGS.dbms == 'mysqlx':
        return generate_row_mysqlx(when, rand_data_buf)
    elif FLAGS.dbms in ['mysql', 'postgres']:
        return generate_row_mysql_pg(when, rand_data_buf)
    else:
        assert False


def generate_pdc_query_mongo(conn, price):
    return (
        conn.find({FLAGS.name_price: {'$gte': price}},
                  projection={FLAGS.name_price: 1, FLAGS.name_ts: 1, FLAGS.name_cust: 1, '_id': 0})
            .sort([(FLAGS.name_price, pymongo.ASCENDING),
                   (FLAGS.name_ts, pymongo.ASCENDING),
                   (FLAGS.name_cust, pymongo.ASCENDING)])
            .limit(FLAGS.rows_per_query)
            .hint([(FLAGS.name_price, pymongo.ASCENDING),
                   (FLAGS.name_ts, pymongo.ASCENDING),
                   (FLAGS.name_cust, pymongo.ASCENDING)])
    )


def generate_pdc_query_mysqlx(conn, price):
    return(
        conn.find('price>=:param')
            .fields([FLAGS.name_price,FLAGS.name_ts,FLAGS.name_cust])
            .sort(FLAGS.name_price, FLAGS.name_ts, FLAGS.name_cust)
            .limit(FLAGS.rows_per_query)
            .bind('param', price)
            .execute()
    )


def generate_pdc_query_mysql_pg(conn, price, force, table_name):
    if force:
        force_txt = 'FORCE INDEX (%s_pdc)' % table_name
    else:
        force_txt = ''

    sql = 'SELECT price,dateandtime,customerid FROM %s %s WHERE ' \
          '(price>=%.2f) ' \
          'ORDER BY price,dateandtime,customerid ' \
          'LIMIT %d' % (FLAGS.table_name, force_txt, price, FLAGS.rows_per_query)
    return sql


def generate_pdc_query(conn, table_name):
    customerid = random.randrange(0, FLAGS.customers)
    price = ((random.random() * FLAGS.max_price) + customerid) / 100.0

    if FLAGS.dbms == 'mongo':
        return generate_pdc_query_mongo(conn, price)
    elif FLAGS.dbms == 'mysqlx':
        return generate_pdc_query_mysqlx(conn, price)
    elif FLAGS.dbms == 'mysql':
        return generate_pdc_query_mysql_pg(conn, price, True, table_name)
    else:
        return generate_pdc_query_mysql_pg(conn, price, False, table_name)


def generate_market_query_mongo(conn, price):
    return (
        conn.find({FLAGS.name_price: {'$gte': price}},
                  projection={FLAGS.name_price: 1, FLAGS.name_cust: 1, '_id': 0})
            .sort([(FLAGS.name_price, pymongo.ASCENDING),
                   (FLAGS.name_cust, pymongo.ASCENDING)])
            .limit(FLAGS.rows_per_query)
            .hint([(FLAGS.name_price, pymongo.ASCENDING),
                   (FLAGS.name_cust, pymongo.ASCENDING)])
    )


def generate_market_query_mysqlx(conn, price):
    return (
        conn.find('price>=:param')
            .fields([FLAGS.name_price, FLAGS.name_cust])
            .sort(FLAGS.name_price,FLAGS.name_cust)
            .limit(FLAGS.rows_per_query)
            .bind('param','price')
            .execute()
    )



def generate_market_query_mysql_pg(conn, price, force, table_name):
    if force:
        force_txt = 'FORCE INDEX (%s_marketsegment)' % table_name
    else:
        force_txt = ''

    sql = 'SELECT price,customerid FROM %s %s WHERE ' \
          '(price>=%.2f) ' \
          'ORDER BY price,customerid ' \
          'LIMIT %d' % (FLAGS.table_name, force_txt, price, FLAGS.rows_per_query)
    return sql


def generate_market_query(conn, table_name):
    customerid = random.randrange(0, FLAGS.customers)
    price = ((random.random() * FLAGS.max_price) + customerid) / 100.0

    if FLAGS.dbms == 'mongo':
        return generate_market_query_mongo(conn, price)
    if FLAGS.dbms == 'mysqlx':
        return generate_market_query_mysqlx(conn, price)
    elif FLAGS.dbms == 'mysql':
        return generate_market_query_mysql_pg(conn, price, True, table_name)
    else:
        return generate_market_query_mysql_pg(conn, price, False, table_name)


def generate_register_query_mongo(conn, cashregisterid):
    return (
        conn.find({FLAGS.name_cash: {'$gte': cashregisterid}},
                  projection={FLAGS.name_cash: 1, FLAGS.name_price: 1, FLAGS.name_cust: 1, '_id': 0})
            .sort([(FLAGS.name_cash, pymongo.ASCENDING),
                   (FLAGS.name_price, pymongo.ASCENDING),
                   (FLAGS.name_cust, pymongo.ASCENDING)])
            .limit(FLAGS.rows_per_query)
            .hint([(FLAGS.name_cash, pymongo.ASCENDING),
                   (FLAGS.name_price, pymongo.ASCENDING),
                   (FLAGS.name_cust, pymongo.ASCENDING)])
    )


def generate_register_query_mysqlx(conn, cashregisterid):
    return(
    conn.find('cashregisterid>:param')
            .fields(['cashregisterid','price','customerid'])
            .sort([FLAGS.name_cash,FLAGS.name_price,FLAGS.name_cust])
            .limit(FLAGS.rows_per_query)
            .bind('param',cashregisterid)
            .execute()
    )



def generate_register_query_mysql_pg(conn, cashregisterid, force, table_name):
    if force:
        force_txt = 'FORCE INDEX (%s_registersegment)' % table_name
    else:
        force_txt = ''

    sql = 'SELECT cashregisterid,price,customerid FROM %s ' \
          '%s WHERE (cashregisterid>%d) ' \
          'ORDER BY cashregisterid,price,customerid ' \
          'LIMIT %d' % (FLAGS.table_name, force_txt, cashregisterid, FLAGS.rows_per_query)
    return sql


def generate_register_query(conn, table_name):
    cashregisterid = random.randrange(0, FLAGS.cashregisters)

    if FLAGS.dbms == 'mongo':
        return generate_register_query_mongo(conn, cashregisterid)
    if FLAGS.dbms == 'mysqlx':
        return generate_register_query_mysqlx(conn, cashregisterid)
    elif FLAGS.dbms == 'mysql':
        return generate_register_query_mysql_pg(conn, cashregisterid, True, table_name)
    else:
        return generate_register_query_mysql_pg(conn, cashregisterid, False, table_name)


def generate_insert_rows(rand_data_buf):
    if FLAGS.dbms == 'mongo':
        when = datetime.utcnow()
    elif FLAGS.dbms == 'mysqlx':
        when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    elif FLAGS.dbms in ['mysql', 'postgres']:
        when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    else:
        assert False

    rows = [generate_row(when, rand_data_buf) \
            for i in range(min(FLAGS.rows_per_commit, FLAGS.max_rows))]

    if FLAGS.dbms == 'mongo':
        return rows
    elif FLAGS.dbms == 'mysqlx':
        return rows
    elif FLAGS.dbms in ['mysql', 'postgres']:
        sql_data = ',\n'.join(rows)
        return 'insert into %s ' \
               '(dateandtime,cashregisterid,customerid,productid,price,data) ' \
               'values %s' % (FLAGS.table_name, sql_data)
    else:
        assert False


def Query(query_args, shared_arr, lock, result_q):
    # block on this until main thread wants all processes to run
    lock.acquire()
    lock.release()

    # print('Query thread running')
    db_conn = get_conn()

    start_time = time.time()
    loops = 0

    if FLAGS.dbms == 'mongo':
        db_thing = db_conn[FLAGS.db_name][FLAGS.table_name]
    elif FLAGS.dbms == 'mysqlx':
        myDB =db_conn.get_schema(FLAGS.db_name)
        db_thing = myDB.get_collection(FLAGS.table_name)
    elif FLAGS.dbms in ['mysql', 'postgres']:
        db_thing = db_conn.cursor()
    else:
        assert False

    rthist = rthist_new()

    done = False
    while not done:
        query_func = random.choice(query_args)

        try:
            query = query_func(db_thing, FLAGS.table_name)

            ts = rthist_start(rthist)

            if FLAGS.dbms == 'mongo':
                count = 0
                for r in query:
                    count += 1
                # if count: print('fetched %d' % count)
                # print('fetched %d' % count)
            elif FLAGS.dbms == 'mysqlx':
                count = 0
                for r in query:
                    count += 1
            elif FLAGS.dbms == 'mysql':
                # print("Query is:", query)
                db_thing.execute(query)
                count = len(db_thing.fetchall())
            elif FLAGS.dbms == 'postgres':
                # print("Query is:", query)
                db_thing.execute(query)
                count = len(db_thing.fetchall())
            else:
                assert False

            rthist_finish(rthist, ts)

        except:
            e = sys.exc_info()[0]
            print("Query exception: ", sys.exc_info())

        loops += 1
        if (loops % 16) == 0:
            shared_arr[1] = loops
            if shared_arr[2] == 1:
                done = True

    if FLAGS.dbms == 'mongo':
        pass
    if FLAGS.dbms == 'mysqlx':
        pass
    elif FLAGS.dbms in ['mysql', 'postgres']:
        db_thing.close()
    else:
        assert False

    db_conn.close()
    result_q.put(rthist_result(rthist, 'Query rt:'))


def get_latest(counters, inserted):
    total = 0
    for c in counters:
        total += c[1]
        c[0] = inserted
    return total


def print_stats(counters, inserted, prev_time, prev_sum, start_time, table_size):
    now = time.time()
    sum_queries = 0

    if FLAGS.query_threads:
        sum_queries = get_latest(counters, inserted)

    nrows = inserted

    print('%d %.1f %.1f %.1f %d %.1f %.0f %.1f %.1f' % (
        nrows,
        now - prev_time,
        now - start_time,
        inserted / (now - start_time),
        table_size,
        FLAGS.rows_per_report / (now - prev_time),
        sum_queries,
        sum_queries / (now - start_time),
        (sum_queries - prev_sum) / (now - prev_time)))
    sys.stdout.flush()
    return now, sum_queries


def Insert(rounds, insert_q, counters, lock):
    # block on this until main thread wants all processes to run
    lock.acquire()
    lock.release()

    # generate insert rows in this loop and place into queue as they're
    # generated.  The execution process will pull them off from here.
    start_time = time.time()
    prev_time = start_time
    inserted = 0

    for c in counters:
        c[0] = inserted

    prev_sum = 0
    table_size = 0
    # we use the tail pointer for deletion - it tells us the first row in the
    # table where we should start deleting
    tail = 0
    sum_queries = 0

    rand_data_buf = base64.b64encode(os.urandom(1024 * 1024 * 4)).decode('ascii')

    rounds_per_second = 0
    if (FLAGS.inserts_per_second):
        rounds_per_second = int(math.ceil(float(FLAGS.inserts_per_second) / FLAGS.rows_per_commit))
        if rounds_per_second < 1:
            rounds_per_second = 1
        last_check = time.time()
        # print("rounds per second = %d" % rounds_per_second)

    for r in range(rounds):
        rows = generate_insert_rows(rand_data_buf)

        insert_q.put(rows)
        inserted += FLAGS.rows_per_commit
        table_size += FLAGS.rows_per_commit

        if (inserted % FLAGS.rows_per_report) == 0:
            prev_time, prev_sum = print_stats(counters, inserted, prev_time, prev_sum,
                                              start_time, table_size)

        # deletes - TODO support for MongoDB * mysqlx
        if FLAGS.with_max_table_rows:
            if table_size > FLAGS.max_table_rows:
                if FLAGS.dbms == 'mongo':
                    assert False
                if FLAGS.dbms == 'mysqlx':
                    assert False
                elif FLAGS.dbms == 'mysql':
                    sql = ('delete from %s where(transactionid>=%d and transactionid<%d);'
                           % (FLAGS.table_name, tail, tail + FLAGS.rows_per_commit))
                else:
                    assert False

                insert_q.put(sql)
                table_size -= FLAGS.rows_per_commit
                tail += FLAGS.rows_per_commit

        # optionally enforce write rate limit
        if rounds_per_second and (r % rounds_per_second) == 0:
            # print("check time on %d" % r)
            now = time.time()
            if now > last_check and now < (last_check + 0.95):
                sleep_time = 1.0 - (now - last_check)
                # print("sleep %s" % sleep_time)
                time.sleep(sleep_time)
            last_check = time.time()

    # block until the queue is empty
    insert_q.put(insert_done)
    insert_q.close()


def statement_executor(stmt_q, lock, result_q):
    # block on this until main thread wants all processes to run
    lock.acquire()
    lock.release()

    db_conn = get_conn()
    if FLAGS.dbms == 'mysql':
        cursor = db_conn.cursor()

        if not FLAGS.unique_checks:
            if FLAGS.engine.lower() == 'rocksdb':
                # cursor.execute('set rocksdb_skip_unique_check=1')
                cursor.execute('set unique_checks=0')
            elif FLAGS.engine.lower() == 'tokudb':
                cursor.execute('set unique_checks=0')

        if FLAGS.bulk_load:
            if FLAGS.engine.lower() == 'rocksdb':
                cursor.execute('set rocksdb_bulk_load=1')

        cursor.close()

    if FLAGS.dbms == 'mongo':
        db = db_conn[FLAGS.db_name]
        mongo_session = None
        if FLAGS.mongo_trx:
            mongo_session = db_conn.start_session()
        mongo_write_concern = pymongo.WriteConcern(w=FLAGS.mongo_w, j=FLAGS.mongo_j)
        collection = db.get_collection(FLAGS.table_name, write_concern=mongo_write_concern)
        print('Using Mongo w=%d, j=%d, trx=%s' % (FLAGS.mongo_w, FLAGS.mongo_j, FLAGS.mongo_trx))

    elif FLAGS.dbms == 'mysqlx':
        db = db_conn.get_schema(FLAGS.db_name)
        mysqlx_session = None
        if FLAGS.mysqlx_trx:
            mysqlx_session=1

       # mongo_write_concern = pymongo.WriteConcern(w=FLAGS.mongo_w, j=FLAGS.mongo_j)
        collection = db.get_collection(FLAGS.table_name)
        print('Using mysqlx  trx=%s' % ( FLAGS.mysqlx_trx))
    elif FLAGS.dbms in ['mysql', 'postgres']:
        cursor = db_conn.cursor()
    else:
        assert False

    rthist = rthist_new()

    while True:
        stmt = stmt_q.get()  # get the statement we need to execute from the queue

        if stmt == insert_done:
            break

        ts = rthist_start(rthist)

        if FLAGS.dbms == 'mongo':
            try:
                # res has type pymongo.InsertManyResult
                if mongo_session:
                    mongo_session.start_transaction(write_concern=mongo_write_concern,
                                                    max_commit_time_ms=1000 * 180)
                res = collection.insert_many(stmt, ordered=True,
                                             bypass_document_validation=False, session=mongo_session)
                assert len(res.inserted_ids) == len(stmt)
                if mongo_session:
                    mongo_session.commit_transaction()
            except pymongo.errors.PyMongoError as e:
                print("Mongo error on insert: ", e)
                raise e
        elif FLAGS.dbms == 'mysqlx':
            try:
                if mysqlx_session:
                    db_conn.start_transaction()

                res = collection.add(stmt).execute()

                assert res.get_affected_items_count() == len(stmt)
                if mysqlx_session:
                    db_conn.commit()
            except Exception as e:
                print("mysqlx error on insert: ", e)
                db_conn.rollback()
                raise e
        elif FLAGS.dbms == 'mysql':
            try:
                cursor.execute(stmt)
            except MySQLdb.Error as e:
                if e[0] != 2006:
                    print("Ignoring MySQL exception: ", e)
                else:
                    raise e
        elif FLAGS.dbms == 'postgres':
            try:
                cursor.execute(stmt)
            except psycopg2.Error as e:
                print("Insert error: %s" % e.pgerror)
                print("Insert error: %s" % e.pgcode)
                print("Insert error: %s" % e.diag)
                raise e
        else:
            assert False

        rthist_finish(rthist, ts)

    stmt_q.close()
    db_conn.close()
    result_q.put(rthist_result(rthist, 'Insert rt:'))


def run_benchmark():
    random.seed(FLAGS.seed)
    rounds = int(math.ceil(float(FLAGS.max_rows) / FLAGS.rows_per_commit))

    # Lock is held until processes can start running
    lock = Lock()
    lock.acquire()

    # Array of tuples, each tuple is (0, num_queries, shutdown flag)
    #   0 might be changed to track number of inserts
    #   num_queries returns number of queries done by query process
    #   shutdown flag is set to 1 when Query process should stop
    counters = []
    query_args = []

    if FLAGS.query_threads:
        query_args.append(generate_pdc_query)
        query_args.append(generate_market_query)
        query_args.append(generate_register_query)

        for i in range(FLAGS.query_threads):
            counters.append(Array('i', [0, 0, 0]))

        query_thr = []
        query_result = Queue()
        for i in range(FLAGS.query_threads):
            query_thr.append(Process(target=Query, args=(query_args, counters[i], lock, query_result)))

    if not FLAGS.no_inserts:
        stmt_q = Queue(4)
        stmt_result = Queue()
        insert_delete = Process(target=statement_executor, args=(stmt_q, lock, stmt_result))
        inserter = Process(target=Insert, args=(rounds, stmt_q, counters, lock))

        # start up the insert execution process with this queue
        insert_delete.start()
        inserter.start()

    # start up the query processes
    if FLAGS.query_threads:
        for qthr in query_thr:
            qthr.start()

    if FLAGS.setup:
        create_table()
        if not FLAGS.secondary_at_end:
            create_index()
            print("create index")
        # print('created table')
    else:
        conn = get_conn()
        conn.close()

    # After the insert and query processes lock/unlock this they can run
    lock.release()
    test_start = time.time()

    if not FLAGS.no_inserts:
        # block until the inserter is done
        insert_delete.join()

        print(stmt_result.get())
        sys.stdout.flush()

        inserter.terminate()
        sys.stdout.flush()
        insert_delete.terminate()

    else:
        start_time = time.time()
        prev_time = start_time
        inserted = 0
        for c in counters:
            c[0] = 0

        prev_sum = 0
        table_size = 0
        sum_queries = 0

        while True:
            time.sleep(10)
            prev_time, prev_sum = \
                print_stats(counters, inserted, prev_time, prev_sum, start_time, table_size)
            if prev_sum >= FLAGS.max_rows:
                break

    if FLAGS.query_threads:
        # Signal Query process to stop
        for i in range(FLAGS.query_threads):
            counters[i][2] = 1

        for qthr in query_thr:
            qthr.join()

        for qthr in query_thr:
            print(query_result.get())
        sys.stdout.flush()

        for qthr in query_thr:
            qthr.terminate()

    if FLAGS.secondary_at_end:
        x_start = time.time()
        create_index()
        x_end = time.time()
        print('Created secondary indexes in %.1f seconds' % (x_end - x_start))

    test_end = time.time()
    print('Totals: %.1f secs, %.1f rows/sec, %s rows' % (
        test_end - test_start,
        FLAGS.max_rows / (test_end - test_start),
        FLAGS.max_rows))
    print('Done')


def main(argv):
    print('#rows #seconds #total_seconds cum_ips table_size last_ips #queries cum_qps last_qps')
    run_benchmark()
    return 0


if __name__ == '__main__':
    new_argv = ParseArgs(sys.argv[1:])
    sys.exit(main([sys.argv[0]] + new_argv))
