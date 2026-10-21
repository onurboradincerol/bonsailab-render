import copy,json,math,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'engine'))
import core,physics
from test_data_completion import request

class FinalReviewTests(unittest.TestCase):
 def test_no_material_or_fixed_addon_preference(self):
  for sp in core.DB['species']:
   t=core.targets(sp,request(sid=sp['id']))
   for m in core.DB['materials']:self.assertEqual(core.base_material_preference(m,sp,t),0)
  self.assertEqual(core.RULES['score']['reference_weight'],0)
  self.assertEqual(core.RULES['score']['fixed_addon_penalty'],0)
 def test_cec_comparison_is_bounded_and_saturates(self):
  self.assertAlmostEqual(core.nutrient_score(0),.5)
  self.assertAlmostEqual(core.nutrient_score(2.5),.125)
  for value in (5,10,50,125,300):self.assertEqual(core.nutrient_score(value),0)
  self.assertGreater(core.nutrient_score(1),core.nutrient_score(4))
  self.assertFalse(core.RULES['nutrient_comparison']['species_optimum_validated'])
 def test_zeolite_can_be_selected_without_forcing_its_presence(self):
  p=request(('Pomza','Lav taşı','Zeolit (Klinoptilolit)'),'T04',grain='medium')
  p['watering']='daily'
  r=core.calculate(p)
  self.assertIn('Zeolit (Klinoptilolit)',[m['name'] for m in r['technical']['selected']])
  self.assertEqual(r['technical']['selection_explanation']['material_name_penalty'],0)
 def test_stable_main_minerals_are_not_limited_by_name(self):
  for sp in core.DB['species']:
   for name in core.PRIMARY:self.assertEqual(core.cap_for(core.BY_NAME[name],sp),100)
 def test_single_akadama_is_calculated(self):
  r=core.calculate(request(('Akadama',),'T04'))
  self.assertEqual(r['technical']['selected'][0]['share'],100)
  self.assertIsNotNone(r['technical']['estimate'])
 def test_sphagnum_and_acid_requirement_use_current_policy(self):
  self.assertGreater(core.cap_for(core.BY_NAME['Sfagnum moss'],core.BY_SPECIES['T10']),0)
  self.assertEqual(core.RULES['acid_min'],0)
  self.assertEqual(core.cap_for(core.BY_NAME['Leonardit'],core.BY_SPECIES['T04']),0)
 def test_public_report_and_search_use_one_ph_value(self):
  r=core.calculate(request(('Kanuma','Kiryu','Zeolit (Klinoptilolit)')))
  for mode in ('technical','economical'):
   if r[mode]['estimate']:
    e=r[mode]['estimate'];self.assertEqual(e['ph_index'],e['chemistry']['mixture_ph'])
 def test_score_breakdown_reconciles_for_additives(self):
  for names in [('Pomza','Torf','Diatomit'),('Pomza','Lav taşı','Zeolit (Klinoptilolit)'),('Pomza','Vermikülit','Akadama')]:
   r=core.calculate(request(names,'T04'))
   v=r['technical'];x=v['selection_explanation']
   self.assertAlmostEqual(v['score'],sum(x[k] for k in ('water_air_score','grain_score','cec_deficit_score','structural_stress_score','ph_sensitivity_score')))
   self.assertEqual(x['material_name_penalty'],0)
   self.assertEqual(x['component_count_penalty'],0)
 def test_cec_mass_volume_and_water_units_reconcile(self):
  p=request(('Pomza','Torf','Perlit'),'T04');sp=core.BY_SPECIES['T04'];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp)
  items=[core.BY_NAME[n] for n in ('Pomza','Torf','Perlit')];e=core.physical_estimate(items,[50,30,20],sp,t,inv)
  masses=e['effective_component_densities'];total=sum(x['dry_mass_g'] for x in masses)
  independent=sum(core.BY_NAME[x['name']]['cec']*x['dry_mass_g'] for x in masses)/total
  self.assertAlmostEqual(e['cec'],independent)
  self.assertAlmostEqual(total,e['dry_mass_g'])
  self.assertAlmostEqual(total,e['density']*e['estimated_final_volume_ml'])
  self.assertAlmostEqual(e['exchange_capacity_cmol'],total/1000*independent)
  self.assertAlmostEqual(e['cec_per_litre_cmol'],independent*e['density'])
  self.assertAlmostEqual(e['available_water_ml'],e['awc']/100*e['estimated_final_volume_ml'])
 def test_integration_converges_at_all_allowed_heights(self):
  for curve in (v['curve'] for v in physics.SCIENCE['pure_curves'].values()):
   for height in (2,8,25,50):self.assertAlmostEqual(physics.capacity(curve,height,128),physics.capacity(curve,height,1024),delta=.01)
 def test_no_candidate_message_uses_chosen_limit(self):
  r=core.calculate({**request(('Perlit',),'T04'),'max_components':1})
  self.assertIn('en fazla 1 bileşen',r['technical']['warnings'][0])
 def test_season_legacy_and_indoor_still_normalize(self):
  p={**request(('Pomza','Lav taşı','Torf'),'T01'),'season':'cool','climate':'indoor'}
  p.pop('location')
  r=core.calculate(p)
  self.assertEqual(r['request']['season'],'year_round');self.assertEqual(r['request']['location'],'indoor')
 def test_all_data_and_source_ids_are_valid(self):
  ids={s['id'] for s in core.DB['sources']}
  self.assertIn('UF_CEC',ids)
  for s in core.DB['species']:self.assertTrue(set(s['source_ids'])<=ids)
  for m in core.DB['materials']:
   for field in ('cc','afp','tp','awc','cec','ph','density'):self.assertTrue(math.isfinite(m[field]))

if __name__=='__main__':unittest.main(verbosity=2)
