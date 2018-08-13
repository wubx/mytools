# Computes read, write and space metrics for a leveled LSM

import sys
import argparse
import math

def range_compares(lsm, args, miss_nobf):
    # returns (seek_cmp, next_cmp)
    #   seek_cmp is number of comparisons to position an iterator per sorted run
    #   next_cmp is number of comparisons per row produced by merging iterator 

    n_sources = args.max_level
    n_sources += 1 # memtable

    # TODO - update for runs per level, and a function of fanout?
    
    # See optimizations in merging iterator. Values determined by simulation.
    # Each entry is (niters, ncmps) where ncmps is the expected number of comparisons
    # per row produced by merging iterator with optimized heap.
    nc = [(1, 0), (2,1), (3,1.18), (4,1.30), (5,1.45), (6,1.47), (7,1.54),
          (9,1.55), (10,1.56)]
    next_cmp = nc[-1][1]
    for niter,ncmp in nc:
      if niter >= n_sources:
        next_cmp = ncmp
        break
    next_cmp += 1 # Comparison to determine when scan can stop

    return miss_nobf, next_cmp

def point_compares(lsm, args):
    # returns the number of comparisons on a point query (hit,miss,miss_nobf)
    # where miss_nobf is number of compares on a miss without bloom filters

    database_mb = 1024.0 * args.database_gb
    hit_cum_cmp = miss_cum_cmp = miss_nobf_cum_cmp = 0
    cum_prob_hit = 0

    # search levels
    for x in xrange(0, args.max_level + 1):
      if x == args.max_level:
        prob_hit = 1 - cum_prob_hit
      else:
        prob_hit =  lsm['level_mb'][x] / database_mb

      hit_cmp = lsm['level_cmp_hit'][x]
      miss_cmp = lsm['level_cmp_miss'][x]
      miss_nobf_cmp = lsm['level_cmp_miss_nobf'][x]
      exp_cmp = (prob_hit * hit_cmp) + ((1 - prob_hit) * miss_cmp)
      hit_cum_cmp += exp_cmp
      miss_cum_cmp += miss_cmp
      miss_nobf_cum_cmp += miss_nobf_cmp
      cum_prob_hit += prob_hit
      print 'L%d cum hit/miss/mnbf %.2f/%.2f/%.2f, level hit/miss/mnbf/ehit %.2f/%.2f/%.2f/%.2f, cum/level phit %.5f/%.5f' % (
          x+1, hit_cum_cmp, miss_cum_cmp, miss_nobf_cum_cmp, hit_cmp, miss_cmp, miss_nobf_cmp, exp_cmp, cum_prob_hit, prob_hit)

    return (hit_cum_cmp, miss_cum_cmp, miss_nobf_cum_cmp)

def cache_overhead(args, mb_per_run, blocks_per_run, uses_bloom, nruns):
  cache_mb = 0.0

  # print 'cache_overhead with mb_per_run %d, blocks_per_file %d, bloom %s, nruns %d' % (
  #    mb_per_run, blocks_per_run, uses_bloom, nruns)

  # memory overhead for bloom filter per run
  bf_mb = 0

  if uses_bloom:
    rows_per_run = math.ceil((mb_per_run * 1024.0 * 1024) / args.row_size)
    bf_bits_per_run = rows_per_run * args.bloom_filter_bits
    bf_mb = bf_bits_per_run / 8 / (1024.0 * 1024)
    cache_mb += bf_mb

  # memory overhead for block indexes per run
  block_index_mb = (blocks_per_run * (args.key_size + args.bytes_per_block_pointer)) / (1024.0 * 1024)
  cache_mb += block_index_mb
  cache_mb *= nruns
  return cache_mb, bf_mb, block_index_mb

def config_lsm_tree(args):
    level_mb = []
    level_files = []
    level_files_cmp = []
    level_cmp_hit = []
    level_cmp_miss = []
    level_cmp_miss_nobf = []
    level_has_bloom = []
    level_nrows = []

    lsm = {}
    blocks_per_file = math.ceil((args.file_mb * 1024.0 * 1024) / args.block_bytes)
    block_index_cmp = math.ceil(math.log(blocks_per_file, 2))
    print 'blocks per file %d, block index compares %d' % (blocks_per_file, block_index_cmp)
    
    rows_per_block = math.ceil((args.block_bytes * 1.0) / args.row_size)
    cmp_per_block = math.ceil(math.log(rows_per_block, 2))
    print 'rows_per_block %d, compare_per_block %d' % (rows_per_block, cmp_per_block)

    database_mb = args.database_gb * 1024.0
    total_fanout = database_mb / (args.memtable_mb * 1.0)
    level_fanout = total_fanout ** (1.0 / args.max_level)
    lsm['level_fanout'] = level_fanout
    lsm['total_fanout'] = total_fanout
    print 'level_fanout %.2d, total_fanout %.2f' % (level_fanout, total_fanout)
    
    # the memtable is L0
    level_mb.append(args.memtable_mb)
    level_files.append(0)
    level_files_cmp.append(0)

    mt_nrows = math.ceil((args.memtable_mb * 1024 * 1024) / args.row_size)
    mt_cmp = math.ceil(math.log(mt_nrows, 2))
    if args.bloom_on_memtable:
      mt_miss_cmp = args.bloom_filter_compares
      mt_hit_cmp = mt_cmp + args.bloom_filter_compares
    else:
      mt_miss_cmp = mt_hit_cmp = mt_cmp

    level_cmp_hit.append(mt_hit_cmp)
    level_cmp_miss.append(mt_miss_cmp)
    level_cmp_miss_nobf.append(mt_cmp)
    level_has_bloom.append(args.bloom_on_memtable)
    level_nrows.append(mt_nrows)

    # setup levels 1 to max
    cur_level = 1
    cur_level_mb = args.memtable_mb * level_fanout
    disk_mb = 0

    for cur_level in xrange(1, args.max_level+1):
      # fix for rounding
      if (cur_level == args.max_level):
        cur_level_mb = database_mb

      level_mb.append(cur_level_mb)
      disk_mb += cur_level_mb

      nfiles = math.ceil(cur_level_mb / args.file_mb)
      level_files.append(nfiles)
      level_files_cmp.append(math.ceil(math.log(nfiles, 2)))

      if cur_level < args.max_level:
        has_bloom = True
      else:
        has_bloom = args.bloom_on_max
      level_has_bloom.append(has_bloom)

      files_only_cmp = level_files_cmp[-1]
      all_cmp = level_files_cmp[-1] + block_index_cmp + cmp_per_block

      if has_bloom:
        hit_cmp = all_cmp + args.bloom_filter_compares
        miss_cmp = files_only_cmp + args.bloom_filter_compares
      else:
        hit_cmp = miss_cmp = all_cmp

      level_cmp_hit.append(hit_cmp)
      level_cmp_miss.append(miss_cmp)
      level_cmp_miss_nobf.append(all_cmp)
      level_nrows.append(math.ceil((cur_level_mb * 1024 * 1024) / args.row_size))

      cur_level_mb = cur_level_mb * level_fanout
      
    lsm['level_mb'] = level_mb
    lsm['level_has_bloom'] = level_has_bloom
    lsm['level_cmp_hit'] = level_cmp_hit
    lsm['level_cmp_miss'] = level_cmp_miss
    lsm['level_cmp_miss_nobf'] = level_cmp_miss_nobf
    lsm['level_nrows'] = level_nrows

    for x in xrange(0, args.max_level + 1):
        print 'L%d: %.2f Mrows, %.2f MB, %d/%d Nfiles/cmp, %d bloom, %d/%d/%d cmp hit/miss/m_nobf' % (
            x, level_nrows[x] / (1024.0*1024), level_mb[x], level_files[x], level_files_cmp[x],
            level_has_bloom[x], level_cmp_hit[x], level_cmp_miss[x], level_cmp_miss_nobf[x])

    # determine CPU and IO write-amp during compaction. CPU is number of compares,
    wa_io_sum = 0
    wa_cpu_sum = 0
    for x in xrange(0, args.max_level + 1):
      if x == 0:
        wa_io = 1
        wa_cpu = 1
      else:
        wa_io = level_fanout * args.wa_fudge
        wa_cpu = wa_io # 1 cmp per KV pair re-written
      wa_io_sum += wa_io
      wa_cpu_sum += wa_cpu
      print 'L%d: write-amp %.2f, comp-cmp %.2f' % (x, wa_io, wa_cpu)
    print 'Compaction total write-amp: io %.2f, cpu %.2f' % (wa_io_sum, wa_cpu_sum)

    # compares for an insert
    insert_cmp = math.ceil(math.log((1024.0 * 1024 * args.memtable_mb) / args.row_size, 2))
    print 'insert compares: %.2f memtable, %.2f memtable + compaction' % (
        insert_cmp, insert_cmp + wa_cpu_sum)

    # space-amp is size-on-disk / logical-size where...
    #   size-on-disk is sum of database file sizes
    #   logical-size is size of live data - assume it is the same
    #     the size of the max LSM level
    print 'space-amp: %.2f' % (disk_mb / database_mb)
    lsm['disk_mb'] = disk_mb

    # Fraction of database that must be in cache so that <= 1 disk reads are done
    # per point lookup. This assumes that everything except max level data blocks
    # are cached.

    # memtable is in memory
    cache_mb = args.memtable_mb
    bf_mb = 0
    if level_has_bloom[0]:
      bf_bits = level_nrows[0] * args.bloom_filter_bits
      bf_mb = bf_bits / 8 / (1024.0 * 1024)
      cache_mb += bf_mb
    print 'L0: cache_mb %.1f, bf_mb %.1f' % (cache_mb, bf_mb)

    # For runs after L0:
    #  block indexes are in memory
    #  bloom filters (if they exist) are in memory
    cache_mb_sum = cache_mb
    for x in xrange(1, args.max_level + 1):
      cache_mb, bf_mb, bi_mb = cache_overhead(args, level_mb[x],
                                              blocks_per_file * level_files[x],
                                              level_has_bloom[x], 1) # TODO runs_per_level
      cache_mb_sum += cache_mb
      print 'L%d: cache_mb %.1f, bf_mb %.1f, bi_mb %.1f' % (x, cache_mb, bf_mb, bi_mb)

    cache_amp = cache_mb_sum / database_mb
    print 'cache_amp %.4f, cache_mb %d' % (cache_amp, cache_mb_sum)
 
    return lsm

def runme(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('--memtable_mb', type=int, default=256)
    parser.add_argument('--wa_fudge', type=float, default=0.8)
    parser.add_argument('--database_gb', type=int, default=1024)
    parser.add_argument('--runs_per_level', type=int, default=1)
    parser.add_argument('--max_level', type=int, default=2)
    parser.add_argument('--row_size', type=int, default=128)
    parser.add_argument('--key_size', type=int, default=8)
    parser.add_argument('--file_mb', type=int, default=32)
    parser.add_argument('--block_bytes', type=int, default=4096)

    parser.add_argument('--bloom_on_max', dest='bloom_on_max', action='store_true')
    parser.add_argument('--no_bloom_on_max', dest='bloom_on_max', action='store_false')
    parser.set_defaults(bloom_on_max=False)

    parser.add_argument('--bloom_on_memtable', dest='bloom_on_memtable', action='store_true')
    parser.add_argument('--no_bloom_on_memtable', dest='bloom_on_memtable', action='store_false')
    parser.set_defaults(bloom_on_memtable=False)

    parser.add_argument('--bloom_filter_bits', type=int, default=10)

    # Assume each bloom filter probe is equivalent to a key comparison
    #
    # RocksDB does bloom_filter_bits * 0.69 probes, rounded down. With
    # bloom_filter_bits=10 this is 6
    parser.add_argument('--bloom_filter_compares', type=int, default=2)

    # The default is a 6-byte pointer
    parser.add_argument('--bytes_per_block_pointer', type=int, default=6)

    r = parser.parse_args(argv)

    x = r.memtable_mb // r.file_mb
    if (r.file_mb * x) != r.memtable_mb:
      print 'file_mb adjusted from %d to %d with mult %d' % (r.file_mb, r.memtable_mb // x, x)
      r.file_mb = r.memtable_mb // x

    print 'memtable_mb ', r.memtable_mb
    print 'wa_fudge ', r.wa_fudge
    print 'database_gb ', r.database_gb
    print 'runs_per_level ', r.runs_per_level
    print 'row_size %d, key_size %d' % (r.row_size, r.key_size)
    print 'file_mb ', r.file_mb
    print 'block_bytes ', r.block_bytes
    print 'bloom_on_max %d, bloom_on_memtable %d' % (r.bloom_on_max, r.bloom_on_memtable)
    print 'bloom_filter_bits %d, bloom_filter_compares %d' % (r.bloom_filter_bits, r.bloom_filter_compares)
    print 'bytes_per_block_pointer ', r.bytes_per_block_pointer
    print 'Mrows %.2f' % (((r.database_gb * 1024 * 1024 * 1024) / r.row_size) / 1000000.0)

    lsm = config_lsm_tree(r)

    hit_cmp, miss_cmp, miss_nobf = point_compares(lsm, r)
    range_seek, range_next = range_compares(lsm, r, miss_nobf) 

    print '\nCompares point hit/miss/mnbf: %.2f\t%.2f\t%.2f' % (hit_cmp, miss_cmp, miss_nobf)
    print '\nCompares range seek/next: %.2f\t%.2f' % (range_seek, range_next)

    return 0

def main(argv):
    return runme(argv)

if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

