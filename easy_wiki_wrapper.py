import requests
import re
import pickle


def clean_bold(t):
    ntest = []
    if "|" not in t:
        nt = t.replace("[", "").replace("]", "").strip()
        ntest.append(nt)
    else:
        if "[[" in t and "]]" in t:
            ix_s, ix_e = t.index("[["), t.index("]]")
            l_string, inner_string, r_string = t[:ix_s].strip(), t[ix_s+2:ix_e], t[ix_e+2:].strip()
            for i in inner_string.split("|"):
                nl = " ".join([l_string, i.strip(), r_string]).strip()
                ntest.append(nl)
    return ntest


class WikiWrapper(object):
    def __init__(self):
        self.url = 'https://en.wikipedia.org/w/api.php'
        self.info_articles = {"des": [set(), set()], "red": [set(), set()], 'ex': [set(), set()]}
        self.point_redirects = {}
        self.local_context = {}
        self.redirects = {}
        self.results = {}
        self.context = {}
        self.categories = {}
        self.search = {}

    def get_search(self, entity_mentioned):
        if entity_mentioned in self.search.keys():
            return self.search[entity_mentioned]
        else:
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'utf8': 1,
                'srsearch': entity_mentioned,
                'srnamespace': '0',
                'srqiprofile': 'engine_autoselect',
                'srprop': '',
                'srlimit': 15
            }

            data = requests.get(self.url, params=params).json()
            o = data["query"]["search"]
            self.search[entity_mentioned] = o
            return o

    def get_categories(self, entity_named, and_hid=False):
        if entity_named in self.categories.keys():
            return self.categories[entity_named]
        else:
            params = {
                'action': 'query',
                'format': 'json',
                'titles': entity_named,
                'prop': 'categories',
                'clshow': ['!hidden', ''][and_hid],
                'cllimit': 'max'
            }

            data = requests.get(self.url, params=params).json()
            p = list(data["query"]["pages"].values())[0]
            o = []
            if "categories" in p.keys():
                o = p["categories"]
            elif "missing" in p.keys():
                o = p["missing"]
            self.categories[entity_named] = o
            return o

    def get_redirects(self, entity_named):
        if entity_named in self.redirects.keys():
            return self.redirects[entity_named]
        else:
            params = {
                'action': 'query',
                'format': 'json',
                'titles': entity_named,
                'prop': 'redirects',
                'rdlimit': 'max',
                "rdnamespace": '0'
            }

            data = requests.get(self.url, params=params).json()
            p = list(data["query"]["pages"].values())[0]
            o = []
            if "redirects" in p.keys():
                o = p["redirects"]
            self.redirects[entity_named] = o
            return o

    def get_local_context(self, entity_named):
        if entity_named in self.local_context.keys():
            return self.local_context[entity_named]
        else:
            params = {
                'action': 'query',
                'origin': '*',
                'prop': 'revisions',
                'format': 'json',
                'titles': entity_named,
                'rvprop': 'content'
            }

            data = requests.get(self.url, params=params).json()
            _p = list(data["query"]["pages"].values())[0]
            p = ""
            if "revisions" in _p.keys():
                p = _p["revisions"][0]["*"]
            lp = len(p)

            b = re.finditer(r"\'{3}[ \w\s\d\[\]\| ]{2,60}\'{3}", p)
            u = {"ix": {}, "dic": []}
            for m in b:
                k = m.group()
                ls = clean_bold(k.replace("'", ""))
                for l in ls:
                    nl = l.lower().strip()
                    if nl not in u["ix"].keys():
                        u["ix"][nl] = [len(u["dic"])]
                    else:
                        u["ix"][nl].append(len(u["dic"]))
                    u["dic"].append({"key": nl, "rank": 1 - m.start() / lp})

            h = re.finditer(r"\[{2}[\w\s\d\|]+\]{2}", p)
            v = {"ix": {}, "dic": []}
            for m in h:
                k = m.group()
                sk = k.replace("[[", "").replace("]]", "").split("|")
                for l in sk:
                    nl = l.lower().strip()
                    if nl not in v["ix"].keys():
                        v["ix"][nl] = [len(v["dic"])]
                    else:
                        v["ix"][nl].append(len(v["dic"]))
                    v["dic"].append({"key": nl, "rank": 1 - m.start() / lp})

            o = {"bold": u, "hlight": v}
            self.local_context[entity_named] = o
            return o

    def get_iolinks(self, entity_named, ides=False):  # inlinks, outlinks (links, linkshere)
        params = {
            'action': 'query',
            'format': 'json',
            'titles': entity_named,
            'prop': 'links|linkshere',
            "pllimit": 'max',
            "lhlimit": 'max'
        }

        data = requests.get(self.url, params=params).json()
        iolinks = list(data["query"]["pages"].values())[0]
        if "linkshere" not in iolinks.keys():
            iolinks["linkshere"] = []
        if "links" not in iolinks.keys():
            iolinks["links"] = []
        if ides:
            ilinks = iolinks["links"]
            o = []
            for i, l in enumerate(ilinks):
                if l["ns"] == 0:
                    is_ex = self._is_(l["title"], t="ex")
                    if is_ex:
                        oi = ilinks[i].copy()
                        is_red = self._is_(l["title"], t="red")
                        if is_red:
                            oi["title"] = self.point_redirects[l["title"]]
                            oi["des"] = self._is_(oi["title"], t="des")
                        else:
                            oi["des"] = self._is_(l["title"], t="des")
                        o.append(oi)
            iolinks["links"] = o
        return iolinks

    def get_results(self, entity_mentioned):
        if entity_mentioned in self.results.keys():
            return self.results[entity_mentioned]
        else:
            searchs = self.get_search(entity_mentioned)
            o = searchs.copy()
            for i, s in enumerate(searchs):
                o[i]["des"] = self._is_(s["title"], t="des")
            self.results[entity_mentioned] = o
            return o

    def _is_(self, entity_named, t):  # t->red, des, ex
        if entity_named in self.info_articles[t][1]:
            return 1
        else:
            if entity_named in self.info_articles[t][0]:
                return 0
            else:
                __ = ("(disambiguation)" not in entity_named.lower()) if t == "des" else True
                if __:
                    cats = self.get_categories(entity_named, and_hid=(t == "red"))
                    if not cats:
                        self.info_articles[t][0].add(entity_named)
                        return 0
                    elif t == "ex":
                        self.info_articles[t][1].add(entity_named)
                        return 1
                    _ = True
                    for c in cats:
                        if {"des": 'Category:Disambiguation pages', "red": "Category:Redirects"}[t] in c["title"]:
                            self.info_articles[t][1].add(entity_named)
                            if t == "red":
                                self.point_redirects[entity_named] = self.get_iolinks(entity_named)["links"][0]["title"]
                                return 1
                            _ = False
                            break
                    if _:
                        self.info_articles[t][0].add(entity_named)
                        return 0
                else:
                    self.info_articles[t][1].add(entity_named)
                    return 1

    def get_context(self, entity_named):
        if entity_named in self.context.keys():
            return self.context[entity_named]
        else:
            iolinks = self.get_iolinks(entity_named)
            redirects = self.get_redirects(entity_named)
            categories = self.get_categories(entity_named)
            local_context = self.get_local_context(entity_named)
            o = {"ilinks": iolinks["links"],
                 "olinks": iolinks["linkshere"],
                 "redirects": redirects,
                 "categories": categories,
                 "bold": local_context["bold"],
                 "hlight": local_context["hlight"]
                 }
            self.context[entity_named] = o
            return o

    def save(self, file_name):
        with open(file_name, 'wb') as file:
            pickle.dump(self, file)

    def load(self, file_name):
        with open(file_name, 'rb') as file:
            new_self = pickle.load(file)
        for k, v in vars(new_self).items():
            self.__dict__[k] = v


if __name__ == "__main__":
    WW = WikiWrapper()
    s = WW.get_search("learning machine")
    # print(s)
    c = WW.get_categories('England', and_hid=False)
    # print(c)
    lc = WW.get_local_context('Blackletter')
    # print(lc)
    cc = WW.get_context("Blackletter")
    # print(cc)

    file_name = "../funcs/test_ww.pickle"
    WW.save(file_name)

    new_WW = WikiWrapper()
    new_WW.load(file_name)
    print(new_WW.categories)

    file_name = "../funcs/ww.pickle"
    new_WW.load(file_name)
    print(new_WW.results.keys())


