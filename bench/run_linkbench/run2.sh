fn=$1
client=$2
ddir=$3
maxid=$4
dname=$5
dop=$6
secs=$7
dbms=$8
dbhost=$9
wf=${10}

if [[ $dbms = "mysql" ]]; then
  echo Skip mstat
  # ps aux | grep python | grep mstat\.py | awk '{ print $2 }' | xargs kill -9 2> /dev/null
  # python mstat.py --loops 1000000 --interval 15 --db_user=root --db_password=pw --db_host=${dbhost} >& r.mstat.$fn &
  # mpid=$!
fi

killall vmstat
killall iostat
iostat -kx 5 >& r.io.$fn &
ipid=$!

vmstat 5 >& r.vm.$fn &
vpid=$!

echo "before $ddir" > r.sz1.$fn
du -sm $ddir >> r.sz1.$fn
echo "before $ddir" > r.sz2.$fn
du -sm $ddir/* >> r.sz2.$fn
echo "before apparent $ddir" > r.asz1.$fn
du -sm --apparent-size $ddir >> r.asz1.$fn
echo "before apparent $ddir" > r.asz2.$fn
du -sm --apparent-size $ddir/* >> r.asz2.$fn

if [[ $dbms = "mongo" ]]; then
  while :; do ps aux | grep "mongod " | grep "storageEngine wiredTiger" | grep -v grep; sleep 5; done >& r.ps.$fn &
  spid=$!
  props=LinkConfigMongoDb2.properties
  logarg=""
elif [[ $dbms = "mysql" ]]; then
  while :; do ps aux | grep "mysqld " | grep basedir | grep datadir | grep -v mysqld_safe | grep -v grep; sleep 5; done >& r.ps.$fn &
  spid=$!
  props=LinkConfigMysql.properties
  $client -uroot -ppw -A -h${dbhost} -e 'reset master'
  logarg="-Duser=root -Dpassword=pw"
elif [[ $dbms = "postgres" ]]; then
  while :; do ps aux | grep "postgres " | grep -v grep; sleep 5; done >& r.ps.$fn &
  spid=$!
  props=LinkConfigPgsql.properties
  logarg="-Duser=linkbench -Dpassword=pw"
else
  echo dbms :: $dbms :: not supported
  exit 1
fi 
echo "background jobs: $ipid $vpid $spid" > r.o.$fn
echo "bash bin/linkbench -c config/${props} -Drequests=5000000000 -Drequesters=$dop -Dmaxtime=$secs -Dmaxid1=$maxid -Dprogressfreq=10 -Ddisplayfreq=10 -Dreq_progress_interval=100000 -Dhost=${dbhost} $logarg -Ddbid=linkdb0 -Dworkload_file=$wf -r" >> r.o.$fn

if ! /usr/bin/time -o r.time.$fn bash bin/linkbench -c config/${props} -Drequests=5000000000 -Drequesters=$dop -Dmaxtime=$secs -Dmaxid1=$maxid -Dprogressfreq=10 -Ddisplayfreq=10 -Dreq_progress_interval=100000 -Dhost=${dbhost} $logarg -Ddbid=linkdb0 -Dworkload_file=$wf -r >> r.o.$fn 2>&1 ; then
  echo Run failed
  exit 1
fi

kill $ipid
kill $vpid
kill $spid
# kill $mpid

if [[ $dbms = "mongo" ]]; then
  cred="-u root -p pw --authenticationDatabase=admin"
  echo "db.serverStatus()" | $client $cred > r.srvstat.$fn
  echo "db.stats()" | $client $cred > r.dbstats.$fn
  echo "db.linktable.stats({indexDetails: true})" | $client $cred linkdb0 > r.stats.link.$fn
  echo "db.nodetable.stats({indexDetails: true})" | $client $cred linkdb0 > r.stats.node.$fn
  echo "db.counttable.stats({indexDetails: true})" | $client $cred linkdb0 > r.stats.count.$fn
  echo "db.linktable.latencyStats({histograms: true}).pretty()" | $client $cred linkdb0 > r.lat.link.$fn
  echo "db.nodetable.latencyStats({histograms: true}).pretty()" | $client $cred linkdb0 > r.lat.node.$fn
  echo "db.counttable.latencyStats({histograms: true}).pretty()" | $client $cred linkdb0 > r.lat.count.$fn
  echo "db.oplog.rs.stats()" | $client $cred local > r.oplog.$fn
  echo "show dbs" | $client $cred linkdb0 > r.dbs.$fn

elif [[ $dbms = "mysql" ]]; then
  $client -uroot -ppw -A -h${dbhost} -e 'reset master'
  $client -uroot -ppw -A -h${dbhost} -e 'show engine innodb status\G' > r.esi.$fn
  $client -uroot -ppw -A -h${dbhost} -e 'show engine rocksdb status\G' > r.esr.$fn
  $client -uroot -ppw -A -h${dbhost} -e 'show engine tokudb status\G' > r.est.$fn
  $client -uroot -ppw -A -h${dbhost} -e 'show global status' > r.gs.$fn
  $client -uroot -ppw -A -h${dbhost} -e 'show global variables' > r.gv.$fn
  $client -uroot -ppw -A -h${dbhost} linkdb0 -e 'show table status' > r.ts.$fn
  $client -uroot -ppw -A -h${dbhost} linkdb0 -e 'show indexes from linktable' > r.is.$fn
  $client -uroot -ppw -A -h${dbhost} linkdb0 -e 'show indexes from nodetable' >> r.is.$fn
  $client -uroot -ppw -A -h${dbhost} linkdb0 -e 'show indexes from counttable' >> r.is.$fn
  $client -uroot -ppw -A -h${dbhost} -e 'show memory status\G' > r.mem.$fn
  $client -uroot -ppw -A -h${dbhost} performance_schema -E -e 'SELECT * FROM table_io_waits_summary_by_table WHERE OBJECT_NAME IN ("linktable", "nodetable", "counttable")' > r.tstat1.$fn
  $client -uroot -ppw -A -h${dbhost} performance_schema -E -e 'SELECT * FROM events_statements_summary_by_account_by_event_name WHERE USER="root"' > r.ustat1.$fn
  $client -uroot -ppw -A -h${dbhost} -E -e 'SELECT * FROM sys.schema_table_statistics WHERE table_name IN ("linktable", "nodetable", "counttable")' > r.tstat2.$fn
  $client -uroot -ppw -A -h${dbhost} -E -e 'SELECT * FROM sys.user_summary' > r.ustat2.$fn
  $client -uroot -ppw -A -h${dbhost} -E -e 'SELECT * FROM information_schema.user_statistics' > r.ustat3.$fn
  $client -uroot -ppw -A -h${dbhost} -E -e 'SELECT * FROM information_schema.table_statistics WHERE TABLE_NAME IN ("linktable", "nodetable", "counttable")' > r.tstat3.$fn
  $client -uroot -ppw -A -h${dbhost} -E -e 'SELECT * FROM information_schema.index_statistics' > r.istat3.$fn
elif [[ $dbms = "postgres" ]]; then
  $client linkbench $pgauth -c 'show all' > o.pg.conf
  $client linkbench $pgauth -x -c 'select * from pg_stat_bgwriter' > r.pgs.bg
  $client linkbench $pgauth -x -c 'select * from pg_stat_database' > r.pgs.db
  $client linkbench $pgauth -x -c 'select * from pg_stat_all_tables' > r.pgs.tabs
  $client linkbench $pgauth -x -c 'select * from pg_stat_all_indexes' > r.pgs.idxs
  $client linkbench $pgauth -x -c 'select * from pg_statio_all_tables' > r.pgi.tabs
  $client linkbench $pgauth -x -c 'select * from pg_statio_all_indexes' > r.pgi.idxs
  $client linkbench $pgauth -x -c 'select * from pg_statio_all_sequences' > r.pgi.seq
else
  echo dbms :: $dbms :: not supported
  exit 1
fi

echo "after $ddir" >> r.sz1.$fn
du -sm $ddir >> r.sz1.$fn
echo "after $ddir" >> r.sz2.$fn
du -sm $ddir/* >> r.sz2.$fn
echo "after $ddir" >> r.asz1.$fn
du -sm --apparent-size $ddir >> r.asz1.$fn
echo "after $ddir" >> r.asz2.$fn
du -sm --apparent-size $ddir/* >> r.asz2.$fn

ips=$( grep "REQUEST PHASE COMPLETED" r.o.$fn | awk '{ print $NF }' )
grep "REQUEST PHASE COMPLETED" r.o.$fn  > r.r.$fn

printf "\nsamp\tr/s\trkb/s\twkb/s\tr/q\trkb/q\twkb/q\tips\n" >> r.r.$fn
grep $dname r.io.$fn | awk '{ rs += $2; rkb += $4; wkb += $5; c += 1 } END { printf "%s\t%.1f\t%.0f\t%.0f\t%.3f\t%.6f\t%.6f\t%s\n", c, rs/c, rkb/c, wkb/c, rs/c/q, rkb/c/q, wkb/c/q, q }' q=$ips >> r.r.$fn

printf "\nsamp\tcs/s\tcpu/s\tcs/q\tcpu/q\n" >> r.r.$fn
grep -v swpd r.vm.$fn | grep -v procs | awk '{ cs += $12; cpu += $13 + $14; c += 1 } END { printf "%s\t%.0f\t%.1f\t%.3f\t%.6f\n", c, cs/c, cpu/c, cs/c/q, cpu/c/q }' q=$ips >> r.r.$fn

echo >> r.r.$fn
head -4 r.sz1.$fn >> r.r.$fn

echo >> r.r.$fn
head -1 r.ps.$fn >> r.r.$fn
tail -1 r.ps.$fn >> r.r.$fn

for op in UPDATE_NODE GET_NODE UPDATE_LINK GET_LINKS_LIST ; do tail -20 r.o.$fn | grep $op | grep main ; done >> r.r.$fn

function dt2s {
  ts=$1
  min=$( echo $ts | tr ':' ' ' | awk '{ print $1 }' )
  sec=$( echo $ts | tr ':' ' ' | awk '{ print $2 }' )
  d2nsecs=$( echo "$min * 60 + $sec" | bc )
  echo $d2nsecs
}

# client CPU seconds
cus=$( cat r.time.$fn | head -1 | awk '{ print $1 }' | sed 's/user//g' )
csy=$( cat r.time.$fn | head -1 | awk '{ print $2 }' | sed 's/system//g' )
csec=$( echo "$cus $csy" | awk '{ printf "%.1f", $1 + $2 }' )

# dbms CPU seconds
# TODO make this work for Postgres
dh=$( cat r.ps.$fn | head -1 | awk '{ print $10 }' )
dt=$( cat r.ps.$fn | tail -1 | awk '{ print $10 }' )
hsec=$( dt2s $dh )
tsec=$( dt2s $dt )
dsec=$( echo "$hsec $tsec" | awk '{ printf "%.1f", $2 - $1 }' )

echo >> r.r.$fn
echo "CPU seconds" >> r.r.$fn
echo "client: $cus user, $csy system, $csec total" >> r.r.$fn
echo "dbms: $dsec " >> r.r.$fn


