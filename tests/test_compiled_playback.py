"""Compiled pack behavior at the runtime/frame and installer boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from codex_pet.pet_pack import bundled_pack, compile_pack
from codex_pet.pet_runtime import PetRuntime, PetVisual
from codex_pet.frames import FrameSource, FrameComposer
from codex_pet.clip_timeline import schedule


class CompiledPlaybackTests(unittest.TestCase):
    def test_robot_runtime_uses_pack_revision_and_physical_frame(self):
        pack = bundled_pack('robot')
        runtime = PetRuntime(PetVisual('robot', 'running'), 10)
        self.assertEqual(runtime.current().revision, pack.revision)
        runtime.tick(12)
        request = runtime.current()
        self.assertEqual(request.reference, 'running/01')
        self.assertEqual(runtime.deadline, 14)
        frame = FrameSource().frame(request.pack_id, request.revision, request.reference)
        self.assertEqual((frame.width, frame.height), (64, 64))
        runtime.sync(PetVisual('robot', 'ready'), 12)
        self.assertIsNone(runtime.deadline)

    def test_robot_long_resume_and_exact_boundary(self):
        runtime = PetRuntime(PetVisual('robot', 'running'), 0)
        started = time.perf_counter()
        for now in (3600, 86400, 10**10):
            runtime.tick(now)
            self.assertEqual(runtime.current().reference, 'running/00')
            self.assertEqual(runtime.deadline, now + 2)
            runtime.tick(now + 2)
            self.assertEqual(runtime.current().reference, 'running/01')
        self.assertLess(time.perf_counter() - started, .1)

    def test_compiled_pixels_and_exposures_match_independent_old_baseline(self):
        baseline = json.loads((Path(__file__).parent / 'fixtures/playback-baseline.json').read_text())
        source, composer = FrameSource(), FrameComposer()
        for key, expected in baseline['cases'].items():
            pet, state, old, cycles, count = key.split('|')
            with self.subTest(path=key):
                pack = bundled_pack(pet)
                pixels = []
                for exposure in schedule(pack, state, int(cycles), from_state=None if old == 'None' else old):
                    frame = composer.compose(source.frame(pet, pack.revision, exposure.reference),
                                             int(count) if state == 'running' else 0)
                    pixels.append((hashlib.sha256(frame.pixels).hexdigest(), exposure.duration_ms))
                self.assertEqual(len(pixels), expected['exposures'])
                self.assertEqual(hashlib.sha256(json.dumps(pixels,separators=(',',':')).encode()).hexdigest(),
                                 expected['sha256'])

    def test_akita_transitions_interruptions_counts_and_cross_pet(self):
        runtime = PetRuntime(PetVisual('akita', 'running', 1), 0)
        self.assertTrue(runtime.sync(PetVisual('akita','ready'),1))
        for offset, reference, deadline in [(0,'ready/05',1.12),(.12,'ready/06',1.24),
                                             (.24,'ready/07',1.36),(.36,'ready/04',1.52),
                                             (1.3,'idle/01',3.1)]:
            runtime.tick(1+offset)
            self.assertEqual(runtime.current().reference,reference)
            self.assertAlmostEqual(runtime.deadline,deadline)
        self.assertFalse(runtime.sync(PetVisual('akita','ready',5),2.4))
        self.assertTrue(runtime.sync(PetVisual('akita','needs_input'),2.4))
        self.assertEqual(runtime.current().reference,'needs_input/00')
        runtime.sync(PetVisual('robot','running'),3)
        runtime.sync(PetVisual('akita','ready'),4)
        self.assertEqual(runtime.current().reference,'ready/04')
        runtime.sync(PetVisual('akita','running',1),5)
        runtime.tick(5.2)
        self.assertTrue(runtime.sync(PetVisual('akita','running',2),5.2))
        self.assertEqual(runtime.current().reference,'running/00')
        self.assertAlmostEqual(runtime.deadline,5.24)

    def test_akita_long_resume_and_hold_have_bounded_work(self):
        running = PetRuntime(PetVisual('akita','running'),0)
        ready = PetRuntime(PetVisual('akita','running'),0)
        ready.sync(PetVisual('akita','ready'),0)
        blocked = PetRuntime(PetVisual('akita','blocked'),0)
        started = time.perf_counter()
        for now,reference,delta in [(3600,'idle/06',.26),(86400,'idle/07',.38)]:
            running.tick(now)
            self.assertEqual(running.current().reference,'running/00')
            self.assertAlmostEqual(running.deadline,now+.04)
            ready.tick(now)
            self.assertEqual(ready.current().reference,reference)
            self.assertAlmostEqual(ready.deadline,now+delta)
            blocked.tick(now)
            self.assertEqual(blocked.current().reference,'blocked/03')
            self.assertIsNone(blocked.deadline)
        self.assertLess(time.perf_counter()-started,.1)

    def test_invalid_manifests_are_rejected_before_pixel_loading(self):
        original = json.loads((Path(__file__).resolve().parents[1] /
                               'codex_pet/assets/robot/pet.json').read_text())
        variants = []
        for key, value in [('schema_version', 2), ('canvas_px', [0,64]),
                           ('canvas_px',[100000,100000]), ('source', {'kind':'builtin','id':'eval'})]:
            row=copy.deepcopy(original); row[key]=value; variants.append(row)
        for duration in (0,-1,True,1.5,None):
            row=copy.deepcopy(original);row['clips']['running']['frames'][0]['duration_ms']=duration;variants.append(row)
        row=copy.deepcopy(original);row['roles']['ready']='missing';variants.append(row)
        row=copy.deepcopy(original);row['clips']['idle']['end']={'mode':'next','clip':'idle'};variants.append(row)
        row=copy.deepcopy(original);row['clips']['running']['frames'][0]['frame']='missing';variants.append(row)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'pet.json'
            for index,row in enumerate(variants):
                with self.subTest(index=index):
                    path.write_text(json.dumps(row))
                    with self.assertRaises(ValueError):
                        compile_pack(path)

if __name__ == '__main__':
    unittest.main()
