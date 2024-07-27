# Take in a log file object and yield lines of can data
import msgpack
import pandas as pd
from typing import List, Union, IO

# from tools.data_processing.can_field_definitions import CAN_FIELDS
from tools.data_processing.msgpack_sorter_unpacker import msgpackFilterUnpacker

from can_field_definitions import CAN_FIELDS
from msgpack_sorter_unpacker import msgpackFilterUnpacker

EXTRA_DISCRIMINATOR_FIELDS = ["sensor_id", "state_id", "actuator"]

def yeild_signatures(payload):
    board_id = payload["board_id"]
    msg_type = payload["msg_type"]
    extra_discriminator = None

    data = payload["data"]

    for field in EXTRA_DISCRIMINATOR_FIELDS:
        if field in data:
            if extra_discriminator is not None:
                raise ValueError("Multiple extra discriminators found in data")
            extra_discriminator = data[field]

    for value in data:
        if value != "time" and value not in EXTRA_DISCRIMINATOR_FIELDS:
            signature = f"{board_id}-{msg_type}{'-' + extra_discriminator if extra_discriminator is not None else ''}-{value}"
            yield signature, value

def get_can_cols(infile: IO) -> List[str]:
    """Get the columns that are present in the CAN data in the file"""

    cols = []  # the colums in the order they're encountered
    cols_set = set()

    # we don't need to use the filtered source, as we're just looking for the message types
    for full_data in msgpack.Unpacker(infile):
        channel, timestamp, payload = full_data  # extract the three parts of the message packed data
        if channel.startswith("CAN/Parsley"):  # CAN messages come over parsely
            # board_id = payload["board_id"]
            # msg_type = payload["msg_type"]
            # data = payload["data"]
            # for value in data:
            #     if value != "time":
            #         signature = (board_id, msg_type, value)
            #         if signature not in cols_set:
            #             cols_set.add(signature)
            #             cols.append(signature)
            for signature, _ in yeild_signatures(payload):
                if signature not in cols_set:
                    cols_set.add(signature)
                    cols.append(signature)

    infile.seek(0)
    return cols


def get_can_lines(infile: IO, cols=[],msg_packed_filtering="behind_stream",placeholder=None) -> pd.DataFrame:
    """Get all the data from the CAN messages in the file, and return it as a list of lists, where each list is a line of the csv"""

    cols_set = set(cols)
    # a dictionary to store the up to date values of the columns we're tracking, so we can output them when we get a new line
    current_info = {col: placeholder for col in cols}
    output_lines = []
    # we use the filtered source to ensure the timestamps are in order for the output data (see msgpack_sorter_unpacker.py for more info on this method and it's FIXME)
    for full_data in msgpack.Unpacker(infile):
        channel, timestamp, payload = full_data
        if channel.startswith("CAN/Parsley"):
            # print(channel,timestamp,payload)

            # we check if the payload matches any of the fields we're tracking, and if it does, we update the current_info dictionary
            matched = False
            # for field in CAN_FIELDS:
            #     if field.match(payload) and field.csv_name in cols_set:
            #         current_info[field.csv_name] = field.read(payload)
            #         matched = True

            # board_id = payload["board_id"]
            # msg_type = payload["msg_type"]
            # data = payload["data"]
            # for value in data:
            #     if value != "time":
            #         signature = (board_id, msg_type, value)
            #         if signature in cols_set:
            #             current_info[signature] = data[value]
            #             matched = True

            for signature, value_key in yeild_signatures(payload):
                if signature in cols_set:
                    current_info[signature] = payload["data"][value_key]
                    matched = True

            # no need for an updated line if we didnt update any of the values we're tracking, we don't want to output a line with no new up to date info
            if not matched:
                continue

            # if we've matched, we should output the current info and write a new line
            output_lines.append({"timestamp": timestamp, **current_info})

            # print(current_info)

    output_df = pd.DataFrame(columns=["timestamp"] + cols, data=output_lines)

    infile.seek(0)
    return output_df


if __name__ == "__main__":
    print("This file is not meant to be run directly. Run main.py instead.")

    # testing code
    # uncomment this code to test the file

    # import argparse
    # parser = argparse.ArgumentParser(description="Run tests for can_processing.py on a real file")
    # parser.add_argument("file", help="The file to test on")
    # args = parser.parse_args()
    # file_path = args.file

    # print("Testing get_can_cols")
    # with open(file_path, "rb") as infile:
    #     print(get_can_cols(infile))
    #     print("Done testing get_can_cols")

    # print("Testing get_can_lines for 10th line")
    # with open(file_path, "rb") as infile:
    #     print(get_can_lines(infile, ['general_status', 'ox_tank', 'injector_valve_cur_status', 'vent_temp', 'vent_valve_status', 'injector_valve_req_status', 'pneumatics_pressure'])[10])
    #     print("Done testing get_can_lines")

    # print("Testing full_extract_can")
    # with open(file_path, "rb") as infile:
    #     with open("test-can-out.csv", "w") as outfile:
    #         writer = csv.writer(outfile)
    #         writer.writerow(["time"] + ['ox_tank', 'injector_valve_cur_status', 'vent_temp', 'vent_valve_status', 'injector_valve_req_status', 'pneumatics_pressure'])
    #         for line in get_can_lines(infile, ['ox_tank', 'injector_valve_cur_status', 'vent_temp', 'vent_valve_status', 'injector_valve_req_status', 'pneumatics_pressure']):
    #             writer.writerow(line)
