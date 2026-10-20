"""Finite numerical estimates from explicit priors, never synthetic measurements.

Ranges describe parameter sensitivity. They are not statistical intervals.
Relative buffering priors are independent of CEC and have no molar units.
"""
import copy,itertools,math

def bounded(x,lo,hi):return max(lo,min(hi,x))

def complete_material(material,policy):
    m=copy.deepcopy(material);imputed=[];transferred=[];aux=policy.get('source_auxiliary',{}).get(m['name'],{})
    for key,default in (('ph',6.5),('cec',15. if m['kind']=='Mineral granül' else 100.),('density',policy['density_g_ml'].get(m['name'],.6 if m['kind']=='Mineral granül' else .2))):
        if m.get(key) is None:
            m[key]=aux['density'] if key=='density' and 'density' in aux else default
            (transferred if key=='density' and 'density' in aux else imputed).append(key)
    if m.get('awc') is None:
        cc=m['tp']*m['cc']/max(1e-12,m['cc']+m['afp'])
        m['awc']=max(0,cc-aux['pwp']) if 'pwp' in aux else cc*policy['awc_fraction_of_cc'].get(m['name'],.45);imputed.append('awc')
    for key in imputed:
        m['provenance'][key]={'class':'ASSUMPTION','sources':['EST23'],'note':'V23 sayısal tamamlama; malzeme ailesi önkabulü. Ürün ölçümü değildir.'}
    for key in transferred:m['provenance'][key]={'class':'MEASURED_OR_MEAN','sources':[aux['source']],'note':'Aynı yayın numunesinden malzeme ailesine aktarım; satın alınan stok ölçümü değildir.'}
    if 'pwp' in aux and 'awc' in imputed:m['provenance']['awc']={'class':'ASSUMPTION','sources':[aux['source'],'V24_RULES'],'note':'CC eksi yayındaki ölçülmüş kullanılamayan su; karışıma aktarım tahminidir.'}
    if not m.get('cec_density_compatible',True):
        m['provenance']['cec']['note']='Aktif model: farklı fraksiyonlardan CEC, korunmuş bileşen kuru kütleleriyle yaklaşık aktarılır; fraksiyon uyumu ve CEC belirsizliği ayrıca korunur.'
        if m.get('chemical_reference'):m['chemical_reference']['note']='CEC ve yoğunluk farklı numune/fraksiyonlara aittir; aktif model bunları tahmini aktarım olarak kullanır, aynı numunede doğrulanmış ölçüm saymaz.'
    m['numeric_estimation']={'reference_transferred_fields':transferred,'imputed_fields':imputed,'source':'EST23','relative_buffer':policy['relative_buffer_per_volume'].get(m['name'],1.)}
    return m

def ratio_range(values_low,values_high,weights_low,weights_high):
    # At positive weights, extrema of a linear-fractional weighted average occur
    # at the corners. Components <=4 in recipes; all 20 remain cheap separately.
    lo=math.inf;hi=-math.inf
    for bits in itertools.product((0,1),repeat=len(weights_low)):
        weights=[weights_high[i] if bit else weights_low[i] for i,bit in enumerate(bits)]
        total=sum(weights)
        lo=min(lo,sum(w*v for w,v in zip(weights,values_low))/total)
        hi=max(hi,sum(w*v for w,v in zip(weights,values_high))/total)
    return lo,hi

def chemical_estimate(materials,shares,policy):
    buffers=[m['numeric_estimation']['relative_buffer']*w/100 for m,w in zip(materials,shares)]
    ph=sum(m['ph']*b for m,b in zip(materials,buffers))/sum(buffers)
    spread=policy['ph_component_half_width'];bmin,bmax=policy['buffer_relative_bounds']
    low,high=ratio_range([max(0,m['ph']-spread) for m in materials],[min(14,m['ph']+spread) for m in materials],
                        [b*bmin for b in buffers],[b*bmax for b in buffers])
    return {'mixture_ph':ph,'range_min':low,'range_max':high,'method':'RELATIVE_BUFFER_PRIOR','estimated':True,
            'buffer_coverage':0,'component_reference_min':min(m['ph'] for m in materials),'component_reference_max':max(m['ph'] for m in materials),
            'used_in_optimization':True,'note':policy['ph_method']+' '+policy['note'],
            'components':[{'name':m['name'],'relative_buffer':m['numeric_estimation']['relative_buffer'],'weighted_buffer':b,'reference_ph':m['ph']} for m,b in zip(materials,buffers)]}

def additional_estimates(materials,shares,states,cc,policy,volume,details=None):
    details=details or {'pwp_delta':0.}
    densities=[state['density'] for state in states]
    mass_weights=[density*w/100 for density,w in zip(densities,shares)]
    premix_density=sum(mass_weights);dry_mass=premix_density*volume
    density=details.get('packed_density',premix_density)
    final_volume=dry_mass/density
    cec=sum(m['cec']*w for m,w in zip(materials,mass_weights))/premix_density
    cmin,cmax=policy['cec_relative_bounds'];dmin,dmax=policy['density_relative_bounds']
    lo,hi=ratio_range([m['cec']*cmin for m in materials],[m['cec']*cmax for m in materials],[w*dmin for w in mass_weights],[w*dmax for w in mass_weights])
    pwp=sum(state['pwp']*w/100 for state,w in zip(states,shares))+details['pwp_delta']
    pwp=bounded(pwp,0,cc);awc=cc-pwp;fraction=awc/max(1e-12,cc);half=policy['awc_fraction_half_width']
    return {'cec':cec,'cec_range_min':lo,'cec_range_max':hi,'density':density,'density_range_min':density*dmin,'density_range_max':density*dmax,
            'dry_mass_g':dry_mass,'input_volume_ml':volume,'premix_density':premix_density,'estimated_final_volume_ml':final_volume,
            'awc':awc,'unavailable_water':pwp,'awc_range_min':cc*max(0,fraction-half),'awc_range_max':cc*min(1,fraction+half),
            'available_water_ml':awc*final_volume/100,'retained_water_ml':cc*final_volume/100,'estimated':True,
            'effective_component_densities':[{'name':m['name'],'density':den,'dry_mass_g':mass*volume} for m,den,mass in zip(materials,densities,mass_weights)],
            'final_volume_basis':'Girdi kuru kütlesi / kaynak karışım yoğunluğu ile son hacim senaryosu. Ölçülmüş büzülme değildir; ürün, fraksiyon ve yöntem farklarını da içerir. Su hacimleri bu tahmini son hacme göredir.',
            'cec_basis':'Bileşen yoğunluğu × karıştırma öncesi girdi hacmi ile kuru kütleler korunur. CEC bu kuru kütlelerle ağırlıklıdır; karışım yoğunluğu bileşen kütlelerini değiştirmez. Farklı fraksiyonların aktarımı tahminidir.',
            'awc_basis':'CC eksi sabit yüksek emişte kullanılamayan su. Torf/kokopit/perlit için Londra 15000 cm su başı; kabuklu seride Gabriel 1.5 MPa ölçümü aktarılır. Yaklaşık yüzde 2 eşik farkı ve paketlenme yöntemi farkı vardır. Eksik numunelerde referans yükseklikte hesaplanan malzeme ailesi önkabulü yükseklik boyunca sabit tutulur.',
            'note':policy['note']}
