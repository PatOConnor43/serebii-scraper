import sys
import time

import postgresql
import requests
import sh
from bs4 import BeautifulSoup
from bs4.element import Tag

import constants

BASE_URL = 'http://www.serebii.net/pokedex-sm/%s.shtml'
EGG_URL = 'http://www.serebii.net/pokedex-sm/egg/%s.shtml'
PORT = sh.cut(
    sh.cut(sh.grep(sh.docker('ps'), ':'), '-d:', '-f2'), '-d-', '-f1').strip()


class LevelUpMove(object):
    def __init__(self, name, level):
        self.name = name
        self.level = level

    def __repr__(self):
        return '{}\nLevel: {}\n'.format(self.name, self.level)


class EggMove(object):
    def __init__(self, name):
        self.name = name
        self.parents_through_level = []
        self.parents_through_breeding = []

    def __repr__(self):
        return '{}\nParents through breeding: {}\nParents through level: {}\n'.format(
            self.name, self.parents_through_breeding,
            self.parents_through_level)


class PokemonEntry(object):
    def __init__(self, name, dex_number):
        self.name = name
        self.dex_number = dex_number
        self.egg_group_1 = ''
        self.egg_group_2 = ''
        self.egg_moves = []
        self.level_up_moves = []

    def __repr__(self):
        return '{} - {} - {} - {}\nEgg Moves: {}\nLevel Up Moves: {}\n'.format(
            self.name, self.dex_number, self.egg_group_1, self.egg_group_2,
            self.egg_moves, self.level_up_moves)

    def populate_level_up_moves_via_dextable(self, table: Tag):
        for tr in table.find_all('tr'):
            level_and_name = tr.find_all(
                'td', attrs={'class': 'fooinfo',
                             'rowspan': '2'})
            if level_and_name:
                level = 0
                try:
                    level = int(level_and_name[0].text)
                except ValueError:
                    pass
                self.level_up_moves.append(
                    LevelUpMove(level_and_name[1].text, level))

    def populate_egg_moves(self):
        print(EGG_URL % self.dex_number)
        resp = requests.get(EGG_URL % self.dex_number)
        soup = BeautifulSoup(resp.text, 'html.parser')
        data = soup.find_all('td', attrs={'class': 'fooinfo'})
        data = [d for d in data if d.a or len(d.contents) == 0 or d.text == '\n']

        self.egg_group_1 = data[0].a.text
        self.egg_group_2 = data[1].a.text if data[1].a else ''
        data = data[2:]

        while len(data) is not 0:
            data = self._handle_bundle(data)

    @staticmethod
    def _parse_parents(data_list):
        return [img.attrs['alt'] for img in data_list.find_all('img')]

    @staticmethod
    def _smeargle_check(data):
        try:
            if data.a and 'pokedex' in data.a.attrs['href']:
                return 'Smeargle' in PokemonEntry._parse_parents(data)
            else:
                return False
        except IndexError:
            return False

    def _handle_bundle(self, bundle):
        move_name = bundle[0].a.text
        egg_move = EggMove(move_name)
        egg_move.parents_through_level = self._parse_parents(bundle[1])
        egg_move.parents_through_breeding = self._parse_parents(bundle[2])
        self.egg_moves.append(egg_move)
        if len(bundle) > 3 and self._smeargle_check(bundle[3]):
            return bundle[4:]
        else:
            return bundle[3:]

pokemon_list = []
def main():

    for dex_num, name in constants.NAMES_BY_NATIONAL_DEX.items():
        print('Handling pokemon: {}'.format(name))
        _handle_entry(dex_num, name)
        time.sleep(1)
    # print(pokemon_list)

    print('initilizing db')
    db = postgresql.open("pq://postgres:password@localhost:{}/postgres".format(
        PORT))
    db.execute(
        "CREATE TABLE pokemon ("
        "pokemon_name text PRIMARY KEY, "
        "dex_number numeric, "
        "egg_group_1 text, "
        "egg_group_2 text"
        ")"
    )
    print('created pokemon table')
    db.execute(
        "CREATE TABLE egg_moves ("
        "pokemon_name text, "
        "move_name text, "
        "level text[], "
        "breeding text[], "
        "PRIMARY KEY(pokemon_name, move_name)"
        ")"
    )
    print('created egg move table')
    db.execute(
        "CREATE TABLE level_up_moves ("
        "pokemon_name text, "
        "move_name text, "
        "level numeric, "
        "PRIMARY KEY(pokemon_name, move_name, level)"
        ")"
    )
    print('created level up move table')
    make_pokemon = db.prepare("INSERT INTO pokemon VALUES ($1, $2, $3, $4)")
    make_egg_move = db.prepare("INSERT INTO egg_moves VALUES ($1, $2, $3, $4)")
    make_level_move = db.prepare("INSERT INTO level_up_moves VALUES ($1, $2, $3)")
    for p in pokemon_list:
        print('inserting {}'.format(p.name))
        make_pokemon(p.name, int(p.dex_number), p.egg_group_1, p.egg_group_2)
        for em in p.egg_moves:
            print('inserting {}'.format(em.name))
            make_egg_move(p.name, em.name, em.parents_through_level, em.parents_through_breeding)
        for lm in p.level_up_moves:
            print('inserting {}'.format(lm.name))
            make_level_move(p.name, lm.name, lm.level)


def _handle_entry(dex_num, name):
    pokemon = PokemonEntry(name, dex_num)
    resp = requests.get(BASE_URL % dex_num)
    # print(resp.text)
    soup = BeautifulSoup(resp.text, 'html.parser')
    dex_tables = soup.find_all(attrs={'class': 'dextable'})
    level_up_table = [t for t in dex_tables if t.tr.td.text == 'Sun/Moon Level Up'][0]
    pokemon.populate_level_up_moves_via_dextable(level_up_table)
    pokemon.populate_egg_moves()
    pokemon_list.append(pokemon)


if __name__ == '__main__':
    main()
