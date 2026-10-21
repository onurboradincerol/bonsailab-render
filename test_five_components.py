import copy,itertools,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'engine'))
import core
from test_data_completion import request

class FiveComponentTests(unittest.TestCase):
 def compare_scalar(self,p):
  sp=core.BY_SPECIES[p['species_id']];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp);mats=[core.BY_NAME[n] for n in inv]
  batch,info=core.search_variants(mats,sp,t,inv,['technical','economical'])
  scalar,reference=core.search_variants_scalar(mats,sp,t,inv,['technical','economical'])
  for mode in batch:
   self.assertEqual(batch[mode][0] if batch[mode] else None,scalar[mode][0] if scalar[mode] else None)
  self.assertEqual(info['candidate_count'],reference['candidate_count'])
  self.assertEqual(info['ph_selection'],reference['ph_selection'])
  self.assertEqual(info['max_components'],5)
  return batch
 def test_batched_search_matches_scalar_with_all_five_subsets_and_couplings(self):
  for names in [('Pomza','Lav taşı','Torf','Perlit','Kokopit'),('Kanuma','Kiryu','Pomza','Torf','Ağaç kabuğu')]:
   for species in ('T04','T32'):
    p=request(names,species);self.compare_scalar(p)
 def test_five_component_recipe_is_found_without_any_feasible_four(self):
  p=request(('Pomza','Lav taşı','Akadama','Kiryu','Torf'),'T04')
  with patch.object(core,'cap_for',return_value=20):
   result=self.compare_scalar(p)['technical']
   self.assertEqual(len(result[2]),5);self.assertEqual(result[3],(20,20,20,20,20))
   output=core.calculate(p)
   self.assertEqual(len(output['technical']['selected']),5)
   self.assertEqual(sum(x['amount_ml'] for x in output['technical']['selected']),2000)
 def test_component_count_does_not_change_score_for_identical_properties(self):
  p=request(('Pomza','Lav taşı','Akadama'),'T04');sp=core.BY_SPECIES['T04'];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp)
  estimate=core.physical_estimate([core.BY_NAME['Pomza'],core.BY_NAME['Lav taşı']],[50,50],sp,t,inv)
  with patch.object(core,'physical_estimate',return_value=estimate),patch.object(core,'base_material_preference',return_value=0),patch.object(core,'grain_fit',return_value=1),patch.object(core,'reference_mix',return_value={}):
   two=core.evaluate([core.BY_NAME[n] for n in ('Pomza','Lav taşı')],[50,50],sp,t,inv)[0]
   three=core.evaluate([core.BY_NAME[n] for n in ('Pomza','Lav taşı','Akadama')],[25,50,25],sp,t,inv)[0]
   self.assertEqual(two,three)
 def test_batched_grid_is_not_a_top_stock_shortlist(self):
  p=request(('Pomza','Lav taşı','Akadama','Kiryu','Torf'),'T04');sp=core.BY_SPECIES['T04'];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp)
  with patch.object(core,'cap_for',return_value=20):
   _,info=core.search_variants([core.BY_NAME[n] for n in inv],sp,t,inv,['technical'])
  self.assertEqual(info['candidate_count'],1)
  self.assertTrue(info['complete']);self.assertEqual(info['material_count'],5)
 def test_each_user_limit_is_respected_and_reported(self):
  p=request(('Pomza','Lav taşı','Torf','Kokopit','Perlit'),'T05')
  fingerprints=set()
  for limit in range(1,6):
   result=core.calculate({**p,'max_components':str(limit)})
   self.assertEqual(result['search']['max_components'],limit)
   self.assertEqual(result['request']['max_components'],limit)
   fingerprints.add(result['request_sha256'])
   for mode in ('technical','economical'):self.assertLessEqual(len(result[mode]['selected']),limit)
  self.assertEqual(len(fingerprints),5)
 def test_invalid_limits_are_rejected_by_api(self):
  import app
  client=app.app.test_client()
  for limit in (0,6,2.5,True,None,'wrong',[],{}):
   with self.subTest(limit=limit):
    response=client.post('/api/calculate',json={**request(),'max_components':limit})
    self.assertEqual(response.status_code,400)
 def test_default_limit_is_five_for_old_saved_requests(self):
  result=core.calculate(request())
  self.assertEqual(result['search']['max_components'],5)
 def test_five_components_can_win_on_quality_without_forcing_the_count(self):
  import json
  case=json.loads((Path(__file__).parent/'tests/cases.json').read_text(encoding='utf8'))[4]['request']
  four=core.calculate({**case,'max_components':4});five=core.calculate({**case,'max_components':5})
  # A larger search space cannot make the winner worse; no fixture forces
  # a five-material recipe after the deliberate V30 objective revision.
  self.assertLessEqual(five['technical']['score'],four['technical']['score']+1e-9)
  self.assertEqual(five['technical']['status'],four['technical']['status'])
 def test_mixed_grains_and_height_match_scalar(self):
  p=request(('Pomza','Torf','Perlit','Kokopit','Ağaç kabuğu'),'T01')
  p['height']=25;p['wind']='strong';p['light']='full';p['watering']='rare'
  for grain in ('fine','medium','coarse'):
   for row in p['inventory']:row['grain_group']=grain
   self.compare_scalar(p)

if __name__=='__main__':unittest.main(verbosity=2)
