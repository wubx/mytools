# max value for --num-threads
maxdop=$1

# base directory for mysql install
ibase=$2

# if yes then run mysql as root else ignore
runasroot=$3

# user, password and database to use
myu=$4
myp=$5
myd=$6

# if yes then enable oprofile else ignore
use_oprofile=$7

# name of storage engine
engine=$8

# number of rows
nr=$9

# test table name
tn=${10}

setup=${11}
insert_only=${12}

vmstat_bin=$( which vmstat )
iostat_bin=$( which iostat )

shift 12
while (( "$#" )) ; do
  b=$1
  shift 1
  mybase=$ibase/$b
  mysql=$mybase/bin/mysql
  mysock=$mybase/var/mysql.sock
  run_mysql="$mysql -u$myu -p$myp -S$mysock $myd"
  echo Running $b from $mybase

  # mv /etc/my.cnf /etc/my.cnf.bak

  $mybase/bin/mysqladmin -u$myu -p$myp -S$mysock shutdown
  if [[ $runasroot == "yes" ]] ; then
    $mybase/bin/mysqld_safe --user=root &
  else
    $mybase/bin/mysqld_safe &
  fi
  sleep 15

  $run_mysql -e 'show variables like "version_comment"'

  if [[ $use_oprofile == "yes" ]]; then
    opcontrol --shutdown
    opcontrol --reset
    opcontrol --setup --no-vmlinux --event=CPU_CLK_UNHALTED:100000:0:0:1 --separate=library
    opcontrol --start
  fi

  if [ ! -z $vmstat_bin ]; then
    $vmstat_bin 60 100000 > ls.v.$engine.$b.nr_$nr &
    vmstat_pid=$!
  fi
  if [ ! -z $iostat_bin ]; then
    $iostat_bin -x 60 100000 > ls.i.$engine.$b.nr_$nr &
    iostat_pid=$!
  fi

  echo Running $b $engine
  bash run1.sh $nr $engine $mysql $maxdop $myu $myp $myd $tn $mysock ls.x.$engine.$b.nr_$nr $setup $insert_only \
      > ls.o.$engine.$b.nr_$nr
  echo -n $b "$engine " > ls.r.$engine.$b.nr_$nr

  grep maxloadtime ls.o.$engine.$b.nr_$nr | awk '{ printf "%s ", $2 }' >> ls.r.$engine.$b.nr_$nr
  echo >> ls.r.$engine.$b.nr_$nr

  $run_mysql -e 'show innodb status\G' >> ls.o.$engine.$b.nr_$nr

  if [ ! -z $vmstat_bin ]; then kill -9 $vmstat_pid; fi
  if [ ! -z $iostat_bin ]; then kill -9 $iostat_pid; fi

  if [[ $use_oprofile == "yes" ]]; then
    opreport --demangle=smart --symbols >> ls.o.$engine.$b.nr_$nr
    opcontrol --shutdown
  fi

  echo Running $b shutdown
  $mybase/bin/mysqladmin -u$myu -p$myp -S$mysock shutdown
  sleep 10
done

