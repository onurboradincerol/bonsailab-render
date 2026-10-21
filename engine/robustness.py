"""Explicit sensitivity scenarios; no source-confidence or material-name penalty.

The stress endpoints are design transfers, not forecasts of a product's lifetime.
Both the exhaustive vector search and public report use these equations.
"""
import numpy as np

def environment(cc, afp, target_cc, target_afp, score):
    dc=np.asarray(cc)-target_cc; da=np.asarray(afp)-target_afp
    return np.where(dc<0,2.,score['cc_excess_weight'])*(dc/9)**2 + np.where(da<0,2.6,score['afp_excess_weight'])*(da/9)**2

def ph_bounds(phs, buffers, shares, policy):
    """Exact box extrema of a positive linear-fractional weighted mean.

    For each endpoint, sorting values means the optimum has one threshold:
    larger weights below the threshold for the minimum, above for the maximum.
    This requires k+1 splits rather than 2**k corners per recipe.
    """
    weights=np.asarray(shares,dtype=float)*np.asarray(buffers,dtype=float)
    lo_factor,hi_factor=policy['buffer_relative_bounds']
    half=policy['ph_component_half_width'];order=np.argsort(phs,kind='stable')
    weights=weights[:,order];values=np.asarray(phs,dtype=float)[order]
    def endpoint(vals,minimum):
        total_w=weights.sum(axis=1);total_n=(weights*vals).sum(axis=1)
        prefix_w=np.zeros(len(weights));prefix_n=np.zeros(len(weights))
        best=total_n/total_w
        for j in range(len(vals)+1):
            left,right=(hi_factor,lo_factor) if minimum else (lo_factor,hi_factor)
            candidate=(right*total_n+(left-right)*prefix_n)/(right*total_w+(left-right)*prefix_w)
            best=np.minimum(best,candidate) if minimum else np.maximum(best,candidate)
            if j<len(vals):prefix_w+=weights[:,j];prefix_n+=weights[:,j]*vals[j]
        return best
    return endpoint(np.maximum(0,values-half),True),endpoint(np.minimum(14,values+half),False)

def assess(cc,tp,organic,ph_low,ph_high,sp,t,rules):
    cc=np.asarray(cc);tp=np.asarray(tp);organic=np.asarray(organic)
    policy=rules['robust_selection'];s=rules['score']
    scenarios=[('initial',cc,tp)]
    # Pore redistribution at constant TP, then an independent settlement stress.
    redistributed=np.minimum(tp,cc+organic*policy['organic_cc_shift_pp'])
    scenarios.append(('redistribution',redistributed,tp))
    settled_tp=np.maximum(0,tp-policy['common_tp_loss_pp']-organic*policy['organic_tp_loss_pp'])
    settled_cc=np.minimum(settled_tp,cc+organic*policy['organic_settlement_cc_shift_pp'])
    scenarios.append(('settlement',settled_cc,settled_tp))
    base=environment(cc,tp-cc,t['target_cc_max'],t['target_afp_max'],s)
    worst=base.copy() if isinstance(base,np.ndarray) else base
    for _,water,porosity in scenarios[1:]:
        worst=np.maximum(worst,environment(water,porosity-water,t['target_cc_max'],t['target_afp_max'],s))
    width=max(policy['min_ph_band_width'],sp['ph_max']-sp['ph_min'])
    ph_score=policy['ph_weight']*((np.maximum(0,sp['ph_min']-ph_low)/width)**2+(np.maximum(0,ph_high-sp['ph_max'])/width)**2)
    return {'base_score':base,'stress_increment':worst-base,'ph_score':ph_score,
            'score':worst+ph_score,'scenarios':scenarios}

def report(items,shares,cc,tp,chemistry,sp,t,rules):
    organic=sum(w for m,w in zip(items,shares) if m['kind']!='Mineral granül')/100
    result=assess(cc,tp,organic,chemistry['range_min'],chemistry['range_max'],sp,t,rules)
    a=rules['acceptance'];cc_floor=max(a['min_cc_floor'],t['target_cc_max']-a['max_cc_deficit']);afp_floor=max(a['min_afp_floor'],t['target_afp_max']-a['max_afp_deficit'])
    scenarios=[{'id':key,'cc':float(water),'tp':float(porosity),'afp':float(porosity-water),
                'physical_floors_met':bool(water>=cc_floor-1e-9 and porosity-water>=afp_floor-1e-9)} for key,water,porosity in result['scenarios']]
    return {'base_score':float(result['base_score']),'structural_stress_score':float(result['stress_increment']),
            'ph_sensitivity_score':float(result['ph_score']),'combined_score':float(result['score']),
            'organic_share_percent':organic*100,'scenarios':scenarios,
            'all_physical_floors_met':all(x['physical_floors_met'] for x in scenarios),
            'ph_range_in_species_band':chemistry['range_min']>=sp['ph_min']-1e-9 and chemistry['range_max']<=sp['ph_max']+1e-9,
            'policy':rules['robust_selection']}
