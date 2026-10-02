#!/usr/bin/env python3
"""Measure production frame preparation and managed cache pressure in one process."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import gc
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from codex_pet.frame_cache import FrameCache  # noqa: E402
from codex_pet.frames import FrameSource,FrameComposer  # noqa: E402
from codex_pet.image_codec import encode_png  # noqa: E402
from codex_pet.pet_runtime import PetRuntime,PetVisual  # noqa: E402
from codex_pet.pet_pack import bundled_pack  # noqa: E402


def rss_kib():
    return next(int(line.split()[1]) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:'))


def probe(rounds=3):
    cache=FrameCache();source,composer=FrameSource(cache),FrameComposer(cache)
    initial_rss=rss_kib();peak_rss=initial_rss;peak_managed=0
    rows=[]
    def prepare(pet,state,count,reference=None):
        started=time.perf_counter_ns()
        request=PetRuntime(PetVisual(pet,state,count),0).current()
        frame=composer.compose(source.frame(pet,request.revision,reference or request.reference),request.count)
        key=('png',frame.key)
        if cache.get(key) is None:cache.put(key,encode_png(frame.width,frame.height,frame.pixels))
        return (time.perf_counter_ns()-started)/1e6
    for pet,state,count in [('akita','idle',0),('akita','running',2),('robot','running',2),
                             ('akita','idle',0),('akita','running',2)]:
        rows.append({'pet':pet,'state':state,'count':count,'prepare_and_encode_ms':prepare(pet,state,count),
                     'cache':asdict(cache.stats()),'rss_kib':rss_kib()})
    started=time.perf_counter();presentations=0
    for _ in range(rounds):
        for pet in ('akita','robot'):
            pack=bundled_pack(pet)
            for state in pack.roles:
                for count in range(26) if state=='running' else (0,):
                    for reference in pack.clips[pack.roles[state]].references:
                        prepare(pet,state,count,reference);presentations+=1
                        peak_managed=max(peak_managed,cache.stats().bytes_used)
                        if presentations%100==0:peak_rss=max(peak_rss,rss_kib())
    result={'method':'Fresh Python process; OS disk cache not flushed; no GUI/native CPU or power measurement.',
            'cold_and_switch':rows,'stress':{'presentations':presentations,'seconds':time.perf_counter()-started,
            'peak_observed_rss_kib':max(peak_rss,rss_kib()),'initial_rss_kib':initial_rss,
            'peak_managed_bytes':peak_managed,'cache':asdict(cache.stats())}}
    cache.clear();gc.collect()
    result['after_clear']={'cache':asdict(cache.stats()),'rss_kib':rss_kib()}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=3)
    args=parser.parse_args()
    if args.rounds<1:parser.error('rounds must be positive')
    result=probe(args.rounds)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(args.output)
