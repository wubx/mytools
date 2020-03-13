dbms_cnf=$1
stopat=$2
dev=$3

dgit=/home/mdcallag/git/mytools/bench/ibench
dpg12=/home/mdcallag/d/pg12
dmy80=/home/mdcallag/d/my80
dmy57=/home/mdcallag/d/my57
dmy56=/home/mdcallag/d/my56
dmyfb=/home/mdcallag/d/fbmy56
dmo40=/home/mdcallag/d/mo40 dmo42=/home/mdcallag/d/mo42
dmo44=/home/mdcallag/d/mo44

qsecs=3600

inmem=5000000
inmemt=5m

iob50m=50000000
iobt50m=50m

iob250m=250000000
iobt250m=250m

iob500m=500000000
iobt500m=500m

iob1g=1000000000
iobt1g=1000m

function do_rx56 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "myrocks $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=rx.$rmemt.dop$dop.c$cnf
  cd $dmyfb; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh rocksdb "" ~/d/fbmy56/bin/mysql /data/m/fbmy/data $dev 1 $dop mysql no no 0 no $rmem no $qsecs >& a.$sfx; sleep 10
  cd $dmyfb; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.rx56.c${cnf}
  mkdir -p $rdir
  mv $dmyfb/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmyfb/etc/my.cnf $rdir
}

function do_in80 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "innodb $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=in.$rmemt.dop$dop.c$cnf
  cd $dmy80; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh innodb "" ~/d/my80/bin/mysql /data/m/my/data $dev 1 $dop mysql no no 0 no $rmem no $qsecs >& a.$sfx; sleep 10
  cd $dmy80; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.in80.c${cnf}
  mkdir -p $rdir
  mv $dmy80/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmy80/etc/my.cnf $rdir
}

function do_in57 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "innodb $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=in.$rmemt.dop$dop.c$cnf
  cd $dmy57; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh innodb "" ~/d/my57/bin/mysql /data/m/my/data $dev 1 $dop mysql no no 0 no $rmem no $qsecs >& a.$sfx; sleep 10
  cd $dmy57; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.in57.c${cnf}
  mkdir -p $rdir
  mv $dmy57/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmy57/etc/my.cnf $rdir
}

function do_in56 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "innodb $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=in.$rmemt.dop$dop.c$cnf
  cd $dmy56; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh innodb "" ~/d/my56/bin/mysql /data/m/my/data $dev 1 $dop mysql no no 0 no $rmem no $qsecs >& a.$sfx; sleep 10
  cd $dmy56; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.in56.c${cnf}
  mkdir -p $rdir
  mv $dmy56/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmy56/etc/my.cnf $rdir
}

function do_pg12 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "postgres $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=pg.$rmemt.dop$dop.c$cnf
  cd $dpg12; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh pg "" ~/d/pg12/bin/psql /data/m/pg/base $dev 1 $dop postgres no no 0 no $rmem no $qsecs none >& a.$sfx; sleep 10
  cd $dpg12; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.pg12.c${cnf}
  mkdir -p $rdir
  mv $dpg12/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dpg12/conf.diff $rdir
}

function do_mo40 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "mongo $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=mo.$rmemt.dop$dop.c$cnf
  cd $dmo40; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh wiredtiger "" ~/d/mo40/bin/mongo /data/m/mo/ $dev 1 $dop mongo yes no 0 no $rmem no $qsecs none >& a.$sfx; sleep 10
  cd $dmo40; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.mo40.c${cnf}
  mkdir -p $rdir
  mv $dmo40/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmo40/mongo.conf $rdir
}

function do_mo42 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "mongo $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=mo.$rmemt.dop$dop.c$cnf
  cd $dmo42; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh wiredtiger "" ~/d/mo42/bin/mongo /data/m/mo/ $dev 1 $dop mongo yes no 0 no $rmem no $qsecs none >& a.$sfx; sleep 10
  cd $dmo42; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.mo42.c${cnf}
  mkdir -p $rdir
  mv $dmo42/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmo42/mongo.conf $rdir
}

function do_mo44 {
  dop=$1
  cnf=$2
  rmemt=$3
  rmem=$4

  echo "mongo $rmemt, dop $dop, conf $cnf at $( date )"
  sfx=mo.$rmemt.dop$dop.c$cnf
  cd $dmo44; bash ini.sh $cnf >& o.ini.$sfx; sleep 10
  cd $dgit; bash iq.sh wiredtiger "" ~/d/mo44/bin/mongo /data/m/mo/ $dev 1 $dop mongo yes no 0 no $rmem no $qsecs none >& a.$sfx; sleep 10
  cd $dmo44; bash down.sh
  cd $dgit
  rdir=${dop}u/$rmemt.mo44.c${cnf}
  mkdir -p $rdir
  mv $dmo44/o.ini.* l end scan q100 q1000 a.$sfx $rdir
  cp $dmo44/mongo.conf $rdir
}

mkdir 1u
mkdir 2u
mkdir 4u

dbms=$( echo $dbms_cnf | tr '.' ' ' | awk '{ print $1 }' )
cnf=$( echo $dbms_cnf | tr '.' ' ' | awk '{ print $2 }' )
echo Run for dbms=$dbms and cnf=$cnf

# test in-memory
for dop in 1 ; do
  if [[ $dbms == "rx56" ]]; then
    do_rx56 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "pg12" ]]; then
    do_pg12 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "in80" ]]; then
    do_in80 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "in57" ]]; then
    do_in57 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "in56" ]]; then
    do_in56 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "mo40" ]]; then
    do_mo40 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "mo42" ]]; then
    do_mo42 $dop $cnf $inmemt $inmem
  elif [[ $dbms == "mo44" ]]; then
    do_mo44 $dop $cnf $inmemt $inmem
  fi  
done

if [[ $stopat == "5m" ]]; then
  echo "stopping at 5m"
  exit 0
fi

# now test io-bound with dop=1
dop=1
if [[ $dbms == "rx56" ]]; then
  do_rx56 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "pg12" ]]; then
  do_pg12 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "in80" ]]; then
  do_in80 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "in57" ]]; then
  do_in57 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "in56" ]]; then
  do_in56 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "mo40" ]]; then
  do_mo40 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "mo42" ]]; then
  do_mo42 $dop $cnf $iobt50m $iob50m
elif [[ $dbms == "mo44" ]]; then
  do_mo44 $dop $cnf $iobt50m $iob50m
fi 

if [[ $stopat == "50m" ]]; then
  echo "stopping at 50m"
  exit 0
fi

dop=1
if [[ $dbms == "rx56" ]]; then
  do_rx56 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "pg12" ]]; then
  do_pg12 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "in80" ]]; then
  do_in80 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "in57" ]]; then
  do_in57 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "in56" ]]; then
  do_in56 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "mo40" ]]; then
  do_mo40 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "mo42" ]]; then
  do_mo42 $dop $cnf $iobt250m $iob250m
elif [[ $dbms == "mo44" ]]; then
  do_mo44 $dop $cnf $iobt250m $iob250m
fi  

if [[ $stopat == "250m" ]]; then
  echo "stopping at 250m"
  exit 0
fi

dop=1
if [[ $dbms == "rx56" ]]; then
  do_rx56 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "pg12" ]]; then
  do_pg12 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "in80" ]]; then
  do_in80 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "in57" ]]; then
  do_in57 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "in56" ]]; then
  do_in56 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "mo40" ]]; then
  do_mo40 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "mo42" ]]; then
  do_mo42 $dop $cnf $iobt500m $iob500m
elif [[ $dbms == "mo44" ]]; then
  do_mo44 $dop $cnf $iobt500m $iob500m
fi  