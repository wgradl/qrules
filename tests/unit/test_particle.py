# pylint: disable=eval-used, no-self-use, redefined-outer-name
# pyright: reportUnusedImport=false
import logging
from copy import deepcopy

import pytest
from attrs.exceptions import FrozenInstanceError
from IPython.lib.pretty import pretty

from qrules.particle import (
    Particle,
    ParticleCollection,
    Spin,
    _get_name_root,
    create_antiparticle,
    create_particle,
)

# For eval tests
from qrules.quantum_numbers import Parity  # noqa: F401


class TestParticle:
    @pytest.mark.parametrize("repr_method", [repr, pretty])
    def test_repr(self, particle_database: ParticleCollection, repr_method):
        for instance in particle_database:
            from_repr = eval(repr_method(instance))
            assert from_repr == instance

    @pytest.mark.parametrize(
        ("name", "is_lepton"),
        [
            ("J/psi(1S)", False),
            ("p", False),
            ("e+", True),
            ("e-", True),
            ("nu(e)", True),
            ("nu(tau)~", True),
            ("tau+", True),
        ],
    )
    def test_is_lepton(
        self, name, is_lepton, particle_database: ParticleCollection
    ):
        assert particle_database[name].is_lepton() == is_lepton

    def test_exceptions(self):
        test_state = Particle(
            name="MyParticle",
            pid=123,
            mass=1.2,
            width=0.1,
            spin=1,
            charge=0,
            isospin=(1, 0),
        )
        with pytest.raises(FrozenInstanceError):
            test_state.charge = 1  # type: ignore[misc]
        with pytest.raises(ValueError, match=r"Fails Gell-Mann–Nishijima"):
            Particle(
                name="Fails Gell-Mann–Nishijima formula",
                pid=666,
                mass=0.0,
                spin=1,
                charge=0,
                parity=-1,
                c_parity=-1,
                g_parity=-1,
                isospin=(0, 0),
                charmness=1,
            )

    def test_eq(self):
        particle = Particle(
            name="MyParticle",
            pid=123,
            mass=1.2,
            spin=1,
            charge=0,
            isospin=(1, 0),
        )
        assert particle != Particle(
            name="MyParticle", pid=123, mass=1.5, width=0.2, spin=1
        )
        same_particle = deepcopy(particle)
        assert particle is not same_particle
        assert particle == same_particle
        assert hash(particle) == hash(same_particle)
        different_labels = Particle(
            name="Different name, same QNs",
            pid=753,
            mass=1.2,
            spin=1,
            charge=0,
            isospin=(1, 0),
        )
        assert particle == different_labels
        assert hash(particle) == hash(different_labels)
        assert particle.name != different_labels.name
        assert particle.pid != different_labels.pid

    @pytest.mark.parametrize(
        ("name1", "name2"),
        [
            # by name
            ("pi0", "a(0)(980)-"),
            # by mass
            ("pi+", "pi-"),
            ("pi-", "pi0"),
            ("pi+", "pi0"),
            ("K0", "K+"),
            # by charge
            ("a(0)(980)+", "a(0)(980)-"),
            ("a(0)(980)+", "a(0)(980)0"),
            ("a(0)(980)0", "a(0)(980)-"),
        ],
    )
    def test_gt(self, name1, name2, particle_database: ParticleCollection):
        pdg = particle_database
        assert pdg[name1] > pdg[name2]

    def test_neg(self, particle_database: ParticleCollection):
        pip = particle_database.find(211)
        pim = particle_database.find(-211)
        assert pip == -pim

    def test_total_ordering(self, particle_database: ParticleCollection):
        pdg = particle_database
        assert [
            particle.name
            for particle in sorted(
                pdg.filter(lambda p: p.name.startswith("f(0)"))
            )
        ] == [
            "f(0)(500)",
            "f(0)(980)",
            "f(0)(1370)",
            "f(0)(1500)",
            "f(0)(1710)",
        ]


class TestParticleCollection:
    def test_init(self, particle_database: ParticleCollection):
        new_pdg = ParticleCollection(particle_database)
        assert new_pdg is not particle_database
        assert new_pdg == particle_database
        with pytest.raises(TypeError):
            ParticleCollection(1)  # type: ignore[arg-type]

    def test_equality(self, particle_database: ParticleCollection):
        assert list(particle_database) == particle_database
        with pytest.raises(NotImplementedError):
            assert particle_database == 0

    @pytest.mark.parametrize("repr_method", [repr, pretty])
    def test_repr(self, particle_database: ParticleCollection, repr_method):
        instance = particle_database
        from_repr = eval(repr_method(instance))
        assert from_repr == instance

    def test_add(self, particle_database: ParticleCollection):
        subset_copy = particle_database.filter(
            lambda p: p.name.startswith("omega")
        )
        subset_copy += particle_database.filter(
            lambda p: p.name.startswith("pi")
        )
        n_subset = len(subset_copy)

        new_particle = create_particle(
            particle_database.find(443),
            pid=666,
            name="EpEm",
            mass=1.0,
            width=0.0,
        )
        subset_copy.add(new_particle)
        assert len(subset_copy) == n_subset + 1
        assert subset_copy["EpEm"] is new_particle

    def test_add_warnings(self, particle_database: ParticleCollection, caplog):
        pions = particle_database.filter(lambda p: p.name.startswith("pi"))
        pi_plus = pions["pi+"]
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            pions.add(create_particle(pi_plus, name="new pi+", mass=0.0))
        assert f"{pi_plus.pid}" in caplog.text
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            pions.add(create_particle(pi_plus, width=1.0))
        assert "pi+" in caplog.text

    @pytest.mark.parametrize("name", ["gamma", "pi0", "K+"])
    def test_contains(self, name: str, particle_database: ParticleCollection):
        assert name in particle_database
        particle = particle_database[name]
        assert particle in particle_database
        assert particle.pid in particle_database

    def test_discard(self, particle_database: ParticleCollection):
        pions = particle_database.filter(lambda p: p.name.startswith("pi"))
        n_pions = len(pions)
        pim = pions["pi-"]
        pip = pions["pi+"]

        pions.discard(pions["pi+"])
        assert len(pions) == n_pions - 1
        assert "pi+" not in pions
        assert pip.name == "pi+"  # still exists

        pions.remove("pi-")
        assert len(pions) == n_pions - 2
        assert pim not in pions
        assert pim.name == "pi-"  # still exists

        with pytest.raises(NotImplementedError):
            pions.discard(111)  # type: ignore[arg-type]

    def test_filter(self, particle_database: ParticleCollection):
        search_result = particle_database.filter(lambda p: "f(0)" in p.name)
        f0_1500_from_subset = search_result["f(0)(1500)"]
        assert len(search_result) == 5
        assert f0_1500_from_subset.mass == 1.506
        assert f0_1500_from_subset is particle_database["f(0)(1500)"]
        assert f0_1500_from_subset is not particle_database["f(0)(980)"]

        search_result = particle_database.filter(lambda p: p.pid == 22)
        gamma_from_subset = search_result["gamma"]
        assert len(search_result) == 1
        assert gamma_from_subset.pid == 22
        assert gamma_from_subset is particle_database["gamma"]
        filtered_result = particle_database.filter(
            lambda p: p.mass > 1.8
            and p.mass < 2.0
            and p.spin == 2
            and p.strangeness == 1
        )
        assert filtered_result.names == [
            "K(2)(1820)0",
            "K(2)(1820)+",
            "K(2)*(1980)0",
            "K(2)*(1980)+",
        ]

    def test_find(self, particle_database: ParticleCollection):
        f2_1950 = particle_database.find(9050225)
        assert f2_1950.name == "f(2)(1950)"
        assert f2_1950.mass == 1.936
        phi = particle_database.find("phi(1020)")
        assert phi.pid == 333
        assert pytest.approx(phi.width) == 0.004249

    @pytest.mark.parametrize(
        ("search_term", "expected"),
        [
            (666, None),
            ("non-existing", None),
            # cspell:disable
            ("gamm", "'gamma'"),
            ("gama", "'gamma', 'Sigma0', 'Sigma-', 'Sigma+', 'Lambda'"),
            (
                "omega",
                "'omega(782)', 'omega(1420)', 'omega(3)(1670)', 'omega(1650)'",
            ),
            ("p~~", "'p~'"),
            ("~", "'p~', 'n~'"),
            ("lambda", "'Lambda', 'Lambda~', 'Lambda(c)+', 'Lambda(b)0'"),
            # cspell:enable
        ],
    )
    def test_find_fail(
        self, particle_database: ParticleCollection, search_term, expected
    ):
        with pytest.raises(LookupError) as exception:
            particle_database.find(search_term)
        if expected is not None:
            message = str(exception.value.args[0])
            message = message.strip("?")
            message = message.strip("]")
            assert message.endswith(expected)

    def test_exceptions(self, particle_database: ParticleCollection):
        gamma = particle_database["gamma"]
        with pytest.raises(
            ValueError,
            match=(
                'Added particle "gamma_new" is equivalent to existing particle'
                ' "gamma"'
            ),
        ):
            particle_database += create_particle(gamma, name="gamma_new")
        with pytest.raises(NotImplementedError):
            particle_database.find(3.14)  # type: ignore[arg-type]
        with pytest.raises(NotImplementedError):
            particle_database += 3.14  # type: ignore[arg-type]
        with pytest.raises(NotImplementedError):
            assert 3.14 in particle_database
        with pytest.raises(AssertionError):
            assert gamma == "gamma"


class TestSpin:
    def test_init_and_eq(self):
        isospin = Spin(1.5, -0.5)
        assert isospin == 1.5
        assert float(isospin) == 1.5
        assert isospin.magnitude == 1.5
        assert isospin.projection == -0.5
        isospin = Spin(1, -0.0)
        assert isinstance(isospin.magnitude, float)
        assert isinstance(isospin.projection, float)
        assert isospin.magnitude == 1.0
        assert isospin.projection == 0.0

    def test_hash(self):
        spin1 = Spin(0.0, 0.0)
        spin2 = Spin(1.5, -0.5)
        assert {spin2, spin1, deepcopy(spin1), deepcopy(spin2)} == {
            spin1,
            spin2,
        }

    @pytest.mark.parametrize(
        ("spin1", "spin2"),
        [
            (Spin(1, 0), Spin(0, 0)),
            (Spin(1, 1), Spin(1, 0)),
            (Spin(1, +1), Spin(1, -1)),
        ],
    )
    def test_gt(self, spin1: Spin, spin2: Spin):
        assert spin1 > spin2

    def test_neg(self):
        isospin = Spin(1.5, -0.5)
        flipped_spin = -isospin
        assert flipped_spin.magnitude == isospin.magnitude
        assert flipped_spin.projection == -isospin.projection

    @pytest.mark.parametrize("repr_method", [repr, pretty])
    @pytest.mark.parametrize(
        "instance", [Spin(2.5, -0.5), Spin(1, 0), Spin(3, -1), Spin(0, 0)]
    )
    def test_repr(self, instance: Spin, repr_method):
        from_repr = eval(repr_method(instance))
        assert from_repr == instance

    @pytest.mark.parametrize(
        ("magnitude", "projection"),
        [(0.3, 0.3), (1.0, 0.5), (0.5, 0.0), (-0.5, 0.5)],
    )
    def test_exceptions(self, magnitude, projection):
        regex_pattern = "|".join(
            [
                r"Spin magnitude \d\.\d has to be a multitude of \d\.[05]",
                r"\(projection - magnitude\) should be integer",
                r"Spin magnitude has to be positive",
            ]
        )
        regex_pattern = f"({regex_pattern})"
        with pytest.raises(ValueError, match=regex_pattern):
            print(Spin(magnitude, projection))


@pytest.mark.parametrize(
    ("particle_name", "anti_particle_name"),
    [("D+", "D-"), ("mu+", "mu-"), ("W+", "W-")],
)
def test_create_antiparticle(
    particle_database: ParticleCollection,
    particle_name,
    anti_particle_name,
):
    template_particle = particle_database[particle_name]
    anti_particle = create_antiparticle(
        template_particle, new_name=anti_particle_name
    )
    comparison_particle = particle_database[anti_particle_name]

    assert anti_particle == comparison_particle


def test_create_antiparticle_tilde(particle_database: ParticleCollection):
    anti_particles = particle_database.filter(lambda p: "~" in p.name)
    assert len(anti_particles) in {
        165,  # particle==0.13
        172,  # particle==0.14, 0.15
        175,  # particle==0.16
    }
    for anti_particle in anti_particles:
        particle_name = anti_particle.name.replace("~", "")
        if "+" in particle_name:
            particle_name = particle_name.replace("+", "-")
        elif "-" in particle_name:
            particle_name = particle_name.replace("-", "+")
        created_particle = create_antiparticle(anti_particle, particle_name)

        assert created_particle == particle_database[particle_name]


def test_create_antiparticle_by_pid(particle_database: ParticleCollection):
    n_particles_with_neg_pid = 0
    for particle in particle_database:
        anti_particles_by_pid = particle_database.filter(
            lambda p: p.pid
            == -particle.pid  # pylint: disable=cell-var-from-loop
        )
        if len(anti_particles_by_pid) != 1:
            continue
        n_particles_with_neg_pid += 1
        anti_particle = next(iter(anti_particles_by_pid))
        particle_from_anti = -anti_particle
        assert particle == particle_from_anti
    assert n_particles_with_neg_pid in [
        428,  # particle==0.13
        442,  # particle==0.14,0.15
        454,  # particle==0.16
    ]


@pytest.mark.parametrize(
    "particle_name",
    ["p", "phi(1020)", "W-", "gamma"],
)
def test_create_particle(
    particle_database: ParticleCollection, particle_name: str
):
    template_particle = particle_database[particle_name]
    new_particle = create_particle(
        template_particle,
        name="testparticle",
        pid=89,
        mass=1.5,
        width=0.5,
    )
    assert new_particle.name == "testparticle"
    assert new_particle.pid == 89
    assert new_particle.charge == template_particle.charge
    assert new_particle.spin == template_particle.spin
    assert new_particle.mass == 1.5
    assert new_particle.width == 0.5
    assert new_particle.baryon_number == template_particle.baryon_number
    assert new_particle.strangeness == template_particle.strangeness


def test_get_name_root(particle_database: ParticleCollection):
    name_roots = {_get_name_root(p.name) for p in particle_database}
    assert name_roots == {
        "a",
        "B",
        "b",
        "chi",
        "D",
        "Delta",
        "e",
        "eta",
        "f",
        "g",
        "gamma",
        "h",
        "J/psi",
        "K",
        "Lambda",
        "mu",
        "N",
        "n",
        "nu",
        "Omega",
        "omega",
        "p",
        "phi",
        "pi",
        "psi",
        "rho",
        "Sigma",
        "tau",
        "Upsilon",
        "W",
        "Xi",
        "Y",
        "Z",
    }
