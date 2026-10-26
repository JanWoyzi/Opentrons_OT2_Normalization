import json
from opentrons import protocol_api, execute
import requests
import sys
sys.path.append("/var/lib/jupyter/notebooks/")


apiLevel = '2.13'
protocol = opentrons.execute.get_protocol_api(apiLevel)

metadata = {
    'apiLevel': apiLevel,
    'protocolName': '1x normalization protocol v2',
    'description': '''Normalization according to DNA bands 
                        Dilution will be performed only if calculated amount is more than 0.5 µl''',
    'author': 'JW'
}

#Variable definitions:
threshold = 20.0 #
h2o_mem = 0.0 #
water_well_index = 0 # source/water well indexing
flag_2x = False # A variable to indicate if two 96-plates are processed or only one --> True = 2x, False = 1x
tips300_list = [] #
tips20_list = [] #

# Must home before running
protocol.home()

# Function to fetch JSON file from laptop
def get_file_content(protocol, filename):
    if requests is None:
        protocol.comment("Requests module not available during simulation")
        return None

    laptop_ip = "169.254.52.0"
    try:
        response = requests.get(f"http://{laptop_ip}:5000/read_file/{filename}")
        if response.status_code == 200:
            return response.json()["content"]
        else:
            protocol.comment(f"Error: {response.json().get('error', 'Unknown error')}")
            return None
    except Exception as e:
        protocol.comment(f"Error fetching file: {str(e)}")
        return None


def run(protocol: protocol_api.ProtocolContext):
    # Fetch the JSON file at the start of the protocol
    h2o_vol_list = get_file_content(protocol,
                                        "C:/Users/Opentrons-PC/Documents/Opentrons documents/Normalisierung/Results/normalization_results.json")

    if h2o_vol_list is None:
        protocol.comment("Failed to fetch JSON file. Aborting protocol.")
        return
    if len(h2o_vol_list) == 2:
        flag_2x = True
        h2o_vol_1st_list[0]
        h2o_vol_2nd_list[1]
    else:
        flag_2x = False
        h2o_vol_1st_list[0]

    #labware definitions:
    tips300_1 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 10)  # tips
    tips300_1.set_offset(x=0.0, y=0.0, z=0.0)
    tips300_list.append(tips300_1)
    tips20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 11)  # tips
    tips20_1.set_offset(x=0.0, y=0.0, z=0.0)
    tips20_list.append(tips20_1)

    if flag_2x:
        tips300_2 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 7)  # tips
        tips300_2.set_offset(x=0.0, y=0.0, z=0.0)
        tips300_list.append(tips300_2)
        tips20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 8)  # tips
        tips20_2.set_offset(x=0.0, y=0.0, z=0.0)
        tips20_list.append(tips20_2)

    water = protocol.load_labware('sarstedtsafeseal_24_aluminumblock_2000ul', 4)  #
    water.set_offset(x=0.0 , y=0.0 , z=0.0)

    # Load Temperature Module 1 in deck slot 3 on USB port 1
    temperature_module1 = protocol.load_module('temperature module gen2', 3)
    temperature_module1.set_offset(x=0.0, y=0.0, z=0.0)

    tm1_1st_dna_source = temperature_module1.load_labware('nest0.2mlpcr8striptubes_96_aluminumblock_200ul',
                                                      label='Temperature-Controlled Tubes')

    if flag_2x:
        # Load Temperature Module 2 in deck slot 6 on USB port 2
        temperature_module2 = protocol.load_module('temperature module gen2', 6)
        temperature_module2.set_offset(x=0.0, y=0.0, z=0.0)

        tm2_2nd_dna_source = temperature_module2.load_labware('nest0.2mlpcr8striptubes_96_aluminumblock_200ul',
                                                      label='Temperature-Controlled Tubes')

    #pipett definitions:
    s_p300 = protocol.load_instrument('p300_single_gen2', 'left',
                                     tip_racks=[tips300_list])  # tip_racks=[tips1, tips2] if more than one rack is needed

    s_p20 = protocol.load_instrument('p20_single_gen2', 'right',
                                     tip_racks=[tips20_list])  # tip_racks=[tips1, tips2] if more than one rack is needed

# start protocol:
    temperature_module1.set_temperature(4)  # in °C, will pause your protocol until your target temperature is reached
    if flag_2x:
        temperature_module2.set_temperature(4)

    s_p300.pick_up_tip()

    for vol01, dest01 in zip(h2o_vol_1st_list, tm1_1st_dna_source.wells()):
        if vol01 > 0.5:  # ignore and go to the next well if transfer amount is lower than 0.5 µl
            h2o_mem = h2o_mem + vol01  # record the total amount of water transfered so far to switch to a new source tube if more than one 2-ml-tube is needed
            if h2o_mem >= 1800.0:  # checks before something is done, if TRUE source (water tube) needs to be switched
                water_well_index = water_well_index+1  # increase the index parameter, used for the source well indexing
                h2o_mem = vol01  # take over the amount that would have "spilled over"
            if vol01 > threshold:
                s_p300.move_to(water.wells()[water_well_index].top())
                # s_p300.touch_tip(v_offset=-2, radius=0.8)
                # s_p300.air_gap(airgap)
                s_p300.aspirate(vol01, water.wells()[water_well_index])
                s_p300.dispense(vol01, dest01.top(z=-3))  # + airgap
                # s_p300.touch_tip(v_offset=-3, radius=0.2)
                s_p300.blow_out()
                # s_p300.touch_tip(v_offset=-3, radius=0.5)
                # s_p300.drop_tip()
            else:
                s_p20.pick_up_tip()
                s_p20.move_to(water.wells()[water_well_index].top())
                s_p20.aspirate(vol01, water.wells()[water_well_index])
                s_p20.dispense(vol01, dest01)  # + airgap
                s_p20.blow_out()
                s_p20.drop_tip()

    if flag_2x:
        for vol02, dest02 in zip(h2o_vol_2nd_list, tm2_2nd_dna_source.wells()):
            if vol02 > 0.5:  # ignore and go to the next well if transfer amount is lower than 0.5 µl
                h2o_mem = h2o_mem + vol02  # record the total amount of water transfered so far to switch to a new source tube if more than one 2-ml-tube is needed
                if h2o_mem >= 1800.0:  # checks before something is done, if TRUE source (water tube) needs to be switched
                    water_well_index = water_well_index + 1  # increase the index parameter, used for the source well indexing
                    h2o_mem = vol02  # take over the amount that would have "spilled over"
                if vol02 > threshold:
                    s_p300.move_to(water.wells()[water_well_index].top())
                    # s_p300.touch_tip(v_offset=-2, radius=0.8)
                    # s_p300.air_gap(airgap)
                    s_p300.aspirate(vol02, water.wells()[water_well_index])
                    s_p300.dispense(vol02, dest02.top(z=-3))  # + airgap
                    # s_p300.touch_tip(v_offset=-3, radius=0.2)
                    s_p300.blow_out()
                    # s_p300.touch_tip(v_offset=-3, radius=0.5)
                    # s_p300.drop_tip()
                else:
                    s_p20.pick_up_tip()
                    s_p20.move_to(water.wells()[water_well_index].top())
                    s_p20.aspirate(vol02, water.wells()[water_well_index])
                    s_p20.dispense(vol02, dest02)  # + airgap
                    s_p20.blow_out()
                    s_p20.drop_tip()

    if s_p20.has_tip:
        s_p20.drop_tip()
    if s_p300.has_tip:
        s_p300.drop_tip()
