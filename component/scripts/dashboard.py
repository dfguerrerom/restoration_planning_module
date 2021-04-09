import ee
import json
import datetime

def _quintile(image, geometry, scale=100):
    """ computes standard quintiles of an image based on an aoi. returns feature collection with quintiles as propeties """ 
    quintile_collection = image.reduceRegion(geometry=geometry, 
                        reducer=ee.Reducer.percentile(percentiles=[20,40,60,80],outputNames=['low','lowmed','highmed','high']), 
                        tileScale=2,
                        scale=scale, 
                        maxPixels=1e13)

    return quintile_collection
def count_quintiles(image, geometry, scale=100):
    histogram_quintile = image.reduceRegion(reducer=ee.Reducer.frequencyHistogram(),
                        geometry=geometry,
                        scale=scale, 
                        # bestEffort=True, 
                        maxPixels=1e13, 
                        tileScale=2)
    return histogram_quintile

def get_image_stats(image, aoi, geeio, scale=100) :
    """ computes quntile breaks and count of pixels within input image. returns feature with quintiles and frequency count"""
    aoi_as_fc = ee.FeatureCollection(aoi)
    # fc_quintile = _quintile(image, aoi)

    # should move quintile norm out of geeio at some point...along with all other utilities
    image_quin, bad_features = geeio.quintile_normalization(image,aoi_as_fc)
    quintile_frequency = count_quintiles(image_quin, aoi)

    out_dict = ee.Dictionary({'suitibility':{'value':quintile_frequency.values()}})
    return out_dict

def get_aoi_count(aoi, name):
    count_aoi = ee.Image.constant(1).rename(name).reduceRegion(**{
                        'reducer':ee.Reducer.count(), 
                        'geometry':aoi,
                        'scale':100,
                        'maxPixels':1e13,
                        })
    return count_aoi
def get_image_percent_cover(image, aoi, name):
    """ computes the percent coverage of a constraint in relation to the total aoi. returns dict name:{value:[],total:[]}"""
    count_img = image.Not().selfMask().reduceRegion(**{
                    'reducer':ee.Reducer.count(), 
                    'geometry':aoi,
                    'scale':100,
                    'maxPixels':1e13,
                    })
    total_img = image.reduceRegion(**{
                    'reducer':ee.Reducer.count(), 
                    'geometry':aoi,
                    'scale':100,
                    'maxPixels':1e13,
                    })
    total_val = ee.Number(total_img.values().get(0))
    count_val = ee.Number(count_img.values().get(0))

    percent = count_val.divide(total_val).multiply(100)
    value = ee.Dictionary({'value':[percent],
                            'total':[total_val]})
    out_dict = ee.Dictionary({name:value})
    return out_dict
    
def get_image_sum(image, aoi, name, mask):
    """ computes the sum of image values not masked by constraints in relation to the total aoi. returns dict name:{value:[],total:[]}"""
     
    sum_img = image.updateMask(mask).reduceRegion(**{
                    'reducer':ee.Reducer.sum(), 
                    'geometry':aoi,
                    'scale':100,
                    'maxPixels':1e13,
                    })
    total_img = image.reduceRegion(**{
                    'reducer':ee.Reducer.sum(), 
                    'geometry':aoi,
                    'scale':100,
                    'maxPixels':1e13,
                    })

    value = ee.Dictionary({'value':sum_img.values(),
                            'total':total_img.values()})
    out_dict = ee.Dictionary({name:value})
    return out_dict

def get_summary_statistics(wlcoutputs, geeio):
    # returns summarys for the dashboard. 
    # {name: values: [],
    #        total: int}
    aoi = geeio.selected_aoi
    count_aoi = get_aoi_count(aoi, 'aoi_count')

    # restoration sutibuility
    wlc, benefits, constraints, costs = wlcoutputs
    mask = ee.ImageCollection(list(map(lambda i : ee.Image(i['eeimage']).rename('c').byte(), constraints))).min()

    # restoration pot. stats
    wlc_summary = get_image_stats(wlc, aoi, geeio)
    try:
        layer_list = geeio.rp_layers_io.layer_list
    except:
        layer_list = layerlist

    # benefits
    # remake benefits from layerlist as original output are in quintiles
    all_benefits_layers = [i for i in layer_list if i['theme'] == 'benefits']
    list(map(lambda i : i.update({'eeimage':ee.Image(i['layer']).unmask() }), all_benefits_layers))

    benefits_out = ee.Dictionary({'benefits':list(map(lambda i : get_image_sum(i['eeimage'],aoi, i['name'], mask), all_benefits_layers))})

    # costs
    costs_out = ee.Dictionary({'costs':list(map(lambda i : get_image_sum(i['eeimage'],aoi, i['name'], mask), costs))})

    #constraints
    constraints_out =ee.Dictionary({'constraints':list(map(lambda i : get_image_percent_cover(i['eeimage'],aoi, i['name']), constraints))}) 

    return wlc_summary.combine(benefits_out).combine(costs_out).combine(constraints_out)

def get_stats_as_feature_collection(wlcoutputs, geeio):
    stats = get_summary_statistics(wlcoutputs, geeio)
    geom = ee.Geometry.Point([0,0])
    feat = ee.Feature(geom).set(stats)
    fc = ee.FeatureCollection(feat)

    return fc
def export_stats(fc):
    now = datetime.datetime.utcnow()
    suffix = now.strftime("%Y%m%d%H%M%S")
    desc = f"restoration_dashboard_{suffix}"
    task = ee.batch.Export.table.toDrive(collection=fc, 
                                     description=desc,
                                     folder='restoration_dashboard',
                                     fileFormat='GeoJSON'
                                    )
    task.start()
    print(task.status())
if __name__ == "__main__":
    # dev
    from test_gee_compute_params import *
    from functions import *
    ee.Initialize()
    io = fake_io()
    io_default = fake_default_io()
    region = fake_aoi_io()
    layerlist = io.layer_list

    aoi = region.get_aoi_ee()
    geeio = gee_compute(region,io,io_default,io)
    # wlcoutputs= geeio.wlc()
    # wlc_out = wlcoutputs[0]

    # test getting as fc for export
    # t7 = get_stats_as_feature_collection(wlcoutputs,geeio)
    # print(t7.getInfo())
    # export_stats(t7)

    # test wrapper
    # t0 = get_summary_statistics(wlcoutputs,geeio)
    # print(t0.getInfo())
    # get wlc quntiles  
    # t1 = get_image_stats(wlc_out, aoi, geeio)
    # print(t1.getInfo())

    # get dict of quintile counts for wlc
    # print(type(wlc_out),wlc_out.bandNames().getInfo())
    # wlc_quintile, bad_features = geeio.quintile_normalization(wlc_out,ee.FeatureCollection(aoi))
    # t2 = count_quintiles(wlc_quintile, aoi)
    # print(t2.getInfo())

    # test getting aoi count
    count_aoi = get_aoi_count(aoi, 'aoi_count')
    print(count_aoi.values().getInfo())
    
    # c = wlcoutputs[2]
    # # print(c)
    # cimg = ee.ImageCollection(list(map(lambda i : ee.Image(i['eeimage']).byte(), c))).min()
    # # print(cimg)

    # a = wlcoutputs[1][0]
    # # print(a)

    # # b = get_image_count(a['eeimage'],aoi, a['name'])
    # # # print(b.getInfo())
    # all_benefits_layers = [i for i in layerlist if i['theme'] == 'benefits']
    # list(map(lambda i : i.update({'eeimage':ee.Image(i['layer']).unmask() }), all_benefits_layers))

    # t = ee.Dictionary({'benefits':list(map(lambda i : get_image_sum(i['eeimage'],aoi, i['name'], cimg), all_benefits_layers))})
    # # # seemingly works... worried a bout total areas all being same, but might be aoi
    # print(t.getInfo())