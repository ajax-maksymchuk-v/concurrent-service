from flask import Flask, jsonify, request
from pymongo import MongoClient
from threading import Lock

app = Flask(__name__)

client = MongoClient('mongodb://10.18.141.14:27017/')
db = client.DEVICE_FARM_BUSY_PHONES
machines_collection = db.AOS

global_lock = Lock()


@app.route('/machines', methods=['GET'])
def get_machines():
    return jsonify({machine['ip']: machine['slots'] for machine in machines_collection.find()})


@app.route('/reserve', methods=['POST'])
def reserve_slots():
    slots_to_reserve = request.json.get('slots_to_reserve', 0)
    machines_to_update = []
    reserved_slots = []
    reserved_count = 0

    with global_lock:
        machines = list(machines_collection.find())
        total_available_slots = sum(
            1 for machine in machines for is_reserved in machine['slots'].values() if not is_reserved
        )
        if total_available_slots < slots_to_reserve:
            return f'Insufficient number of slots, available is {total_available_slots}', 400
        for machine in machines:
            if reserved_count >= slots_to_reserve:
                break
            for slot_id, is_reserved in list(machine['slots'].items()):
                if not is_reserved:
                    machine['slots'][slot_id] = True
                    reserved_count += 1
                    machines_to_update.append((machine['ip'], machine['slots']))
                    reserved_slots.append(f'{slot_id}/{machine["ip"]}')
                    if reserved_count == slots_to_reserve:
                        break

        for machine_ip, slots in machines_to_update:
            machines_collection.update_one({'ip': machine_ip}, {'$set': {'slots': slots}})

        if reserved_count == slots_to_reserve:
            return ','.join(reserved_slots)


@app.route('/release', methods=['POST'])
def release_slots():
    slots_to_release = request.json.get('slots_to_release', []).split(',')
    released_slots = []

    with global_lock:
        for slot in slots_to_release:
            slot_id, machine_ip = slot.split('/')
            machine = machines_collection.find_one({'ip': machine_ip})
            if machine and slot_id in machine['slots'] and machine['slots'][slot_id]:
                machine['slots'][slot_id] = False
                machines_collection.update_one({'ip': machine_ip}, {'$set': {'slots': machine['slots']}})
                released_slots.append(slot)

    if released_slots:
        return ', '.join(released_slots)
    else:
        return 'Nothing to release, all given slots was been released', 400


@app.route('/add_machine', methods=['POST'])
def add_machine():
    machine_ip = request.json.get('ip')
    number_of_slots = request.json.get('number_of_slots', 0)
    selected_slots = [f'emulator-555{4 + i * 2}' for i in range(number_of_slots)]

    if machines_collection.find_one({'ip': machine_ip}):
        return 'Machine already exists', 400

    machines_collection.insert_one({'ip': machine_ip, 'slots': {slot: False for slot in selected_slots}})
    return f'Machine {machine_ip} successfully added'


if __name__ == '__main__':
    app.run(debug=True, port=1234)
