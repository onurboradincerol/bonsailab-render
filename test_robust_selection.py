import copy,hashlib,itertools,json,math,random,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'engine'))
import core,robustness,estimates
from test_data_completion import request

class RobustSelectionTests(unittest.TestCase):
 def test_continuous_goal_has_no_zero_penalty_plateau(self):
  sp=core.BY_SPECIES['T14'];t=core.targets(sp,request(sid='T14'))
  target=core.environment_score(sp,t,t['target_cc_max'],t['target_afp_max'],6)
  shifted=core.environment_score(sp,t,t['target_cc_max']+1,t['target_afp_max']+1,6)
  self.assertEqual(target,0);self.assertGreater(shifted,target)
 def test_exact_ph_extrema_match_independent_corner_enumeration(self):
  rng=random.Random(31);policy=core.DB['numeric_estimation']
  for k in range(1,6):
   for _ in range(20):
    ph=[rng.uniform(.1,13.9) for j in range(k)];b=[rng.uniform(.1,8) for j in range(k)];w=[rng.uniform(1,100) for j in range(k)]
    low,high=robustness.ph_bounds(ph,b,[w],policy);half=policy['ph_component_half_width'];a,z=policy['buffer_relative_bounds']
    corners=[]
    for factors in itertools.product((a,z),repeat=k):
     weights=[x*y*f for x,y,f in zip(w,b,factors)];den=sum(weights)
     corners.append((sum(max(0,p-half)*v for p,v in zip(ph,weights))/den,sum(min(14,p+half)*v for p,v in zip(ph,weights))/den))
    self.assertAlmostEqual(float(low[0]),min(x[0] for x in corners));self.assertAlmostEqual(float(high[0]),max(x[1] for x in corners))
 def test_ph_range_changes_score_even_when_point_is_unchanged(self):
  sp=core.BY_SPECIES['T14'];t=core.targets(sp,request(sid='T14'))
  narrow=robustness.assess(40,70,0,5.6,6.7,sp,t,core.RULES)
  wide=robustness.assess(40,70,0,4.9,7.8,sp,t,core.RULES)
  self.assertEqual(float(narrow['ph_score']),0);self.assertGreater(float(wide['ph_score']),0)
 def test_scenario_conservation_and_common_mineral_settlement(self):
  sp=core.BY_SPECIES['T14'];t=core.targets(sp,request(sid='T14'))
  for organic in (0,.1,.4,1):
   d=robustness.assess(40,70,organic,5.6,6.7,sp,t,core.RULES)
   for _,cc,tp in d['scenarios']:
    self.assertTrue(0<=float(cc)<=float(tp)<=100)
   self.assertAlmostEqual(float(d['scenarios'][2][2]),70-3-8*organic)
   self.assertGreaterEqual(float(d['stress_increment']),0)
 def test_rank_has_no_count_or_name_field(self):
  sp=core.BY_SPECIES['T14'];a=[{'id':'M01','name':'AAA'},{'id':'M02','name':'ZZZ'}]
  b=[{'id':'M01','name':'ZZZ'},{'id':'M02','name':'AAA'}]
  r=core.selection_rank(0,0,6,sp,1,a,[40,60]);renamed=core.selection_rank(0,0,6,sp,1,b,[40,60])
  three=core.selection_rank(0,0,6,sp,1,a+[{'id':'M03','name':'DDD'}],[20,40,40])
  self.assertEqual(r,renamed);self.assertEqual(r[:-1],three[:-1]);self.assertEqual(len(r),7)
  self.assertEqual(r[-1],hashlib.sha256(b'[["M01",40],["M02",60]]').hexdigest())
 def test_ties_across_component_counts_are_counted_and_neutral(self):
  p=request(('Akadama','Kiryu'),'T04');p['max_components']=2
  sp=core.BY_SPECIES['T04'];t=core.targets(sp,p);inv=core.inputs_with_inventory(p,sp)[0]
  original=core.prepare_material
  def same(m,stock):
   x=original(m,stock);x.update(ph=6.,cec=20.);x['numeric_estimation']['relative_buffer']=1.;return x
  state={'cc':40.,'tp':70.,'reference_cc':40.,'height_delta':0.,'basis':'LEGACY_ASSUMPTION','source':None,'curve':None,'pwp':10.,'density':.5,'source_coverage':0,'source_evidence':0}
  with patch.object(core,'prepare_material',side_effect=same),patch.object(core,'component_state',return_value=state):
   batch,info=core.search_variants([core.BY_NAME[n] for n in inv],sp,t,inv,['technical'])
   scalar,other=core.search_variants_scalar([core.BY_NAME[n] for n in inv],sp,t,inv,['technical'])
  self.assertEqual(info['selection_equivalence']['technical']['count'],21)
  self.assertEqual(info['selection_equivalence'],other['selection_equivalence']);self.assertEqual(batch['technical'][0],scalar['technical'][0])
 def test_full_breakdown_and_scenarios_for_every_species(self):
  for sp in core.DB['species']:
   r=core.calculate(request(('Pomza','Lav taşı','Torf','Zeolit (Klinoptilolit)'),sp['id']))
   for mode in ('technical','economical'):
    v=r[mode]
    if not v['estimate']:continue
    x=v['selection_explanation'];e=v['estimate'];a=e['robustness']
    self.assertAlmostEqual(v['score'],sum(x[k] for k in ('water_air_score','grain_score','cec_deficit_score','structural_stress_score','ph_sensitivity_score')))
    self.assertEqual(len(a['scenarios']),3);self.assertGreaterEqual(v['selection_equivalence']['count'],1)
    for scenario in a['scenarios']:self.assertAlmostEqual(scenario['cc']+scenario['afp'],scenario['tp'])
    self.assertFalse(a['policy']['validated_biological_optimum'])
 def test_carmona_old_winner_is_not_a_zero_score_optimum(self):
  p=request(('Pomza','Akadama','Kiremit irmiği','Ağaç kabuğu'),'T14',grain='fine')
  p.update(climate='mediterranean',phase='pre',watering='twice')
  r=core.calculate(p);sp=core.BY_SPECIES['T14'];t=core.targets(sp,p);inv=core.inputs_with_inventory(p,sp)[0]
  score,e=core.evaluate([core.BY_NAME['Kiremit irmiği'],core.BY_NAME['Ağaç kabuğu']],[60,40],sp,t,inv,'economical')
  self.assertGreater(score,0);self.assertGreater(e['robustness']['ph_sensitivity_score'],0)
  self.assertLess(r['economical']['score'],score)
  self.assertNotEqual([(x['name'],x['share']) for x in r['economical']['selected']],[('Kiremit irmiği',60),('Ağaç kabuğu',40)])
 def test_initial_point_in_band_does_not_claim_range_acceptance(self):
  p=request(('Akadama',),'T14');v=core.calculate(p)['technical'];e=v['estimate']
  if not e['robustness']['ph_range_in_species_band']:self.assertEqual(v['status'],'conditional')
 def test_source_class_is_not_an_uncertainty_penalty(self):
  p=request(('Akadama','Pomza','Lav taşı'),'T14');sp=core.BY_SPECIES['T14'];t=core.targets(sp,p);inv=core.inputs_with_inventory(p,sp)[0]
  items=[copy.deepcopy(core.BY_NAME[n]) for n in ('Akadama','Pomza','Lav taşı')]
  before=core.evaluate(items,[50,30,20],sp,t,inv)[0]
  for m in items:
   for row in m['provenance'].values():row['class']='MISSING'
  after=core.evaluate(items,[50,30,20],sp,t,inv)[0]
  self.assertEqual(before,after)
 def test_inventory_order_does_not_resolve_equal_candidates(self):
  p=request(('Akadama','Pomza','Lav taşı','Ağaç kabuğu'),'T14')
  first=core.calculate(p);p['inventory'].reverse();second=core.calculate(p)
  for mode in ('technical','economical'):
   self.assertEqual(first[mode]['selected'],second[mode]['selected'])
   self.assertEqual(first[mode]['selection_equivalence'],second[mode]['selection_equivalence'])

if __name__=='__main__':unittest.main(verbosity=2)
