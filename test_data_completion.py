import copy,itertools,json,math,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent/'engine'))
import core,estimates,physics

def request(names=('Kanuma','Pomza','Torf','Kiryu'),sid='T32',grain='fine'):
 return {'species_id':sid,'climate':'mild','season':'year_round','phase':'nebari','pot':'air','height':8,'volume':2000,'location':'outdoor','light':'filtered','wind':'low','watering':'twice','inventory':[{'name':n,'available':True,'grain_group':grain if core.BY_NAME[n]['grain_applicable'] else None} for n in names]}
def signature(result):
 return {mode:([ (x['name'],x['share']) for x in result[mode]['selected']],result[mode].get('score'),result[mode]['status']) for mode in ('technical','economical')}

class CompletionTests(unittest.TestCase):
 def test_20_materials_have_140_finite_valid_reference_values(self):
  self.assertEqual(len(core.DB['materials']),20)
  for m in core.DB['materials']:
   for key in ('ph','cec','cc','afp','tp','awc','density'):
    self.assertIsInstance(m[key],(int,float));self.assertTrue(math.isfinite(m[key]));self.assertNotEqual(m['provenance'][key]['class'],'MISSING')
   self.assertTrue(0<=m['awc']<=m['cc']<=m['tp']<=100)
   self.assertAlmostEqual(m['cc']+m['afp'],m['tp'],places=3)
   self.assertTrue(0<=m['ph']<=14);self.assertGreater(m['density'],0)
 def test_source_ids_and_estimate_methods_are_resolved(self):
  ids={s['id'] for s in core.DB['sources']};self.assertEqual(len(ids),len(core.DB['sources']))
  for m in core.DB['materials']:
   for p in m['provenance'].values():self.assertTrue(set(p['sources'])<=ids)
   self.assertFalse(m['data_completion']['penalized_in_selection'])
 def test_every_material_all_grains_all_heights_has_valid_phases(self):
  sp=core.BY_SPECIES['T32']
  for m in core.DB['materials']:
   for grain in ('fine','medium','coarse') if m['grain_applicable'] else (None,):
    stock={'grain_group':grain,'min_mm':core.BY_GRAIN[grain]['min_mm'] if grain else None,'max_mm':core.BY_GRAIN[grain]['max_mm'] if grain else None}
    prepared=core.prepare_material(m,stock);previous=math.inf
    for height in (2,4,8,12,25,50):
     state=core.component_state(prepared,height)
     self.assertTrue(0<=state['pwp']<=state['cc']<=state['tp']<=100,(m['name'],grain,height,state))
     self.assertLessEqual(state['cc'],previous+1e-8);previous=state['cc']
 def test_missing_evidence_cannot_change_score_rank_or_selected_recipe(self):
  p=request()
  with patch.object(core,'measure_quality',return_value=0):low=core.calculate(p)
  with patch.object(core,'measure_quality',return_value=1):high=core.calculate(p)
  self.assertEqual(signature(low),signature(high))
 def test_unknown_source_fraction_cannot_change_score_rank_or_selected_recipe(self):
  original=core.prepare_material
  def override(value):
   def f(*args):
    m=original(*args);m['source_size_fit']=value;return m
   return f
  with patch.object(core,'prepare_material',side_effect=override(None)):unknown=core.calculate(request())
  with patch.object(core,'prepare_material',side_effect=override(1)):known=core.calculate(request())
  self.assertEqual(signature(unknown),signature(known))
 def test_provenance_never_changes_soft_tier_for_any_species(self):
  for sp in core.DB['species']:
   t=core.targets(sp,request(sid=sp['id']))
   lo=core._soft_risk(sp,t,t['target_cc_max'],t['target_afp_max'],1,0,0,6)
   hi=core._soft_risk(sp,t,t['target_cc_max'],t['target_afp_max'],1,1,100,6)
   self.assertEqual(lo,hi)
 def test_availability_is_not_a_technical_recipe_score_penalty(self):
  p=request();sp=core.BY_SPECIES['T32'];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp);items=[core.BY_NAME['Kanuma'],core.BY_NAME['Pomza']]
  before=core.evaluate(items,[80,20],sp,t,inv)[0]
  with patch.object(core,'hard_to_source',return_value=False):after=core.evaluate(items,[80,20],sp,t,inv)[0]
  self.assertEqual(before,after)
 def test_real_grain_mismatch_still_affects_score(self):
  p=request(('Pomza','Torf'));sp=core.BY_SPECIES['T32'];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp)
  score=core.evaluate([core.BY_NAME[n] for n in ('Pomza','Torf')],[75,25],sp,t,inv)[0]
  with patch.object(core,'grain_fit',return_value=0):bad=core.evaluate([core.BY_NAME[n] for n in ('Pomza','Torf')],[75,25],sp,t,inv)[0]
  self.assertGreater(bad,score)
 def test_kanuma_height_response_is_estimated_and_nonconstant(self):
  m=core.prepare_material(core.BY_NAME['Kanuma'],{'grain_group':'fine','min_mm':2,'max_mm':5})
  shallow=physics.material_state(m,4);deep=physics.material_state(m,16)
  self.assertEqual(shallow['basis'],'ESTIMATED_REFERENCE_CURVE');self.assertGreater(shallow['cc'],deep['cc'])
  self.assertAlmostEqual(physics.material_state(m,12)['cc'],m['cc'],places=6)
 def test_source_curve_reference_values_reconcile(self):
  for name in physics.SCIENCE['pure_curves']:
   m=core.BY_NAME[name];state=physics.pure_state(name,12)
   self.assertAlmostEqual(m['cc'],state['cc']);self.assertAlmostEqual(m['awc'],state['cc']-state['pwp']);self.assertAlmostEqual(m['density'],state['density'])
 def test_pumice_interpolation_recovers_measured_anchor(self):
  m=core.prepare_material(core.BY_NAME['Pomza'],{'grain_group':'medium','min_mm':4,'max_mm':7})
  anchor=core.BY_NAME['Pomza']['reference_profiles'][1]
  for key in ('cc','afp','tp','awc','density'):self.assertAlmostEqual(m[key],anchor[key])
 def test_completed_estimates_keep_provenance_after_runtime_preparation(self):
  m=core.prepare_material(core.BY_NAME['Kanuma'],{'grain_group':'fine','min_mm':2,'max_mm':5})
  self.assertIn('awc',m['numeric_estimation']['imputed_fields']);self.assertFalse(m['numeric_estimation']['penalized_in_selection'])
 def test_accelerated_search_matches_independent_public_recipe_evaluation(self):
  p=request(('Kanuma','Pomza','Torf'));sp=core.BY_SPECIES['T32'];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp);mats=sorted([core.BY_NAME[n] for n in inv],key=lambda m:m['name'])
  solutions,_=core.search_variants(mats,sp,t,inv,['technical'])
  ranked=[]
  for k in range(1,4):
   for items in itertools.combinations(mats,k):
    for shares in itertools.product(range(5,101,5),repeat=k):
     if sum(shares)!=100 or not core.layout_valid(items,shares,sp,inv):continue
     score,e=core.evaluate(items,shares,sp,t,inv);ranked.append(core.candidate_rank(items,shares,sp,t,inv,score,e,'technical'))
  self.assertEqual(solutions['technical'][0],min(ranked))

if __name__=='__main__':unittest.main(verbosity=2)
