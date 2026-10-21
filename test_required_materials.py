import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'engine'))
import core
from test_data_completion import request,signature

POOL=('Pomza','Lav taşı','Ağaç kabuğu','Zeolit (Klinoptilolit)','Torf')

def require(payload,*names):
 for row in payload['inventory']:row['required']=row['name'] in names
 return payload

class RequiredMaterialTests(unittest.TestCase):
 def test_legacy_requests_and_explicit_false_are_equivalent(self):
  legacy=core.calculate(request(POOL,'T14'))
  explicit=core.calculate(require(request(POOL,'T14')))
  self.assertEqual(signature(legacy),signature(explicit))
  self.assertEqual(legacy['request_sha256'],explicit['request_sha256'])
  self.assertEqual(legacy['request_identity_version'],3)
  self.assertTrue(all(row['required'] is False for row in legacy['request']['inventory']))

 def test_force_optional_ingredient_and_keep_caps(self):
  p=require(request(POOL,'T14'),'Zeolit (Klinoptilolit)','Ağaç kabuğu')
  output=core.calculate(p)
  self.assertEqual(output['search']['required_materials'],sorted(('Zeolit (Klinoptilolit)','Ağaç kabuğu')))
  for mode in ('technical','economical'):
   result=output[mode];self.assertNotEqual(result['status'],'unavailable')
   rows={row['name']:row for row in result['selected']}
   self.assertTrue(all(rows[n]['required'] and rows[n]['share']>0 for n in ('Zeolit (Klinoptilolit)','Ağaç kabuğu')))
   self.assertEqual(sum(row['share'] for row in rows.values()),100)
   for n,row in rows.items():self.assertLessEqual(row['share'],output['limits'][n])
  unforced=core.calculate(require(request(POOL,'T14')))
  self.assertNotEqual(output['request_sha256'],unforced['request_sha256'])

 def test_five_required_materials_use_all_five(self):
  p=require(request(POOL,'T14'),*POOL);result=core.calculate(p)
  self.assertEqual({row['name'] for row in result['technical']['selected']},set(POOL))
  self.assertTrue(all(row['required'] for row in result['technical']['selected']))
  self.assertEqual(sum(row['share'] for row in result['technical']['selected']),100)

 def test_single_material_limit_and_one_required_material(self):
  p=require(request(('Pomza','Lav taşı'),'T14'),'Pomza');p['max_components']=1
  for mode in ('technical','economical'):
   rows=core.calculate(p)[mode]['selected'];self.assertEqual([(r['name'],r['share']) for r in rows],[('Pomza',100)])

 def test_required_difficult_stock_is_not_silently_removed_from_alternative(self):
  p=require(request(('Akadama','Pomza','Lav taşı'),'T14'),'Akadama');result=core.calculate(p)
  self.assertIn('Akadama',{r['name'] for r in result['technical']['selected']})
  self.assertEqual(result['economical']['status'],'unavailable');self.assertEqual(result['economical']['selected'],[])
  self.assertIn('çakışıyor',result['economical']['warnings'][0])

 def test_api_rejects_conflicting_and_non_boolean_required_values(self):
  import app
  client=app.app.test_client();payloads=[]
  for value in (1,0,'true','false',None,[],{}):
   p=request(('Pomza','Lav taşı'),'T14');p['inventory'][0]['required']=value;payloads.append(p)
  p=require(request(('Pomza','Lav taşı'),'T14'),'Pomza');p['inventory'][0]['available']=False;payloads.append(p)
  p=require(request(POOL,'T14'),*POOL);p['max_components']=4;payloads.append(p)
  p=require(request(('Pomza','Leonardit'),'T14'),'Leonardit');payloads.append(p)
  for p in payloads:
   with self.subTest(payload=p):self.assertEqual(client.post('/api/calculate',json=p).status_code,400)

 def test_impossible_forced_structure_is_explicitly_unavailable(self):
  p=require(request(('Torf','Kokopit'),'T14'),'Torf');result=core.calculate(p)
  for mode in ('technical','economical'):
   self.assertEqual(result[mode]['status'],'unavailable')
   self.assertIn('Zorunlu malzemeleri',result[mode]['warnings'][0])

 def test_layout_validation_rejects_missing_required_material(self):
  p=require(request(('Pomza','Lav taşı'),'T14'),'Lav taşı');sp=core.BY_SPECIES['T14'];inv,_,_=core.inputs_with_inventory(p,sp)
  self.assertFalse(core.layout_valid([core.BY_NAME['Pomza']],[100],sp,inv))
  self.assertTrue(core.layout_valid([core.BY_NAME[n] for n in ('Pomza','Lav taşı')],[50,50],sp,inv))

 def test_scalar_and_batch_match_with_required_and_couplings(self):
  for species in ('T14','T32'):
   p=require(request(POOL,species),'Zeolit (Klinoptilolit)','Torf');sp=core.BY_SPECIES[species];t=core.targets(sp,p);inv,_,_=core.inputs_with_inventory(p,sp);mats=[core.BY_NAME[n] for n in inv]
   batch,bi=core.search_variants(mats,sp,t,inv,['technical','economical'])
   scalar,si=core.search_variants_scalar(mats,sp,t,inv,['technical','economical'])
   for mode in batch:self.assertEqual(batch[mode][0] if batch[mode] else None,scalar[mode][0] if scalar[mode] else None)
   self.assertEqual(bi['candidate_count'],si['candidate_count']);self.assertEqual(bi['ph_selection'],si['ph_selection'])

 def test_all_species_keep_required_ingredient_in_each_available_result(self):
  for sp in core.DB['species']:
   p=require(request(POOL,sp['id']),'Zeolit (Klinoptilolit)');result=core.calculate(p)
   for mode in ('technical','economical'):
    rows=result[mode]['selected'];self.assertTrue(rows,(sp['name'],mode))
    self.assertTrue(any(r['name']=='Zeolit (Klinoptilolit)' and r['share']>0 and r['required'] for r in rows))
    self.assertEqual(sum(r['share'] for r in rows),100);self.assertLessEqual(len(rows),5)

if __name__=='__main__':unittest.main(verbosity=2)
