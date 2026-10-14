"""Static seed data. Book rows themselves come from data/books.json (your original file)."""

CATEGORIES = [
    ("cse", "Computer Science"),
    ("ece", "Electronics"),
    ("eee", "Electrical"),
    ("civil", "Civil Engineering"),
]

# code, percent, minimum cart value, max discount
COUPONS = [
    ("WELCOME10", 10, 300, 150),
    ("BOOKS20", 20, 1000, 400),
    ("STUDENT5", 5, 0, 100),
]

BOOK_DESCRIPTIONS = {
    1: "A clear, practical introduction to data structures and algorithm analysis, with worked examples that bridge theory and implementation.",
    2: "The standard text on how operating systems manage processes, memory, storage and security, known as the 'dinosaur book'.",
    3: "A layered tour of computer networking from the physical wire up to applications, written with Tanenbaum's trademark clarity.",
    4: "Comprehensive coverage of relational design, SQL, transactions, storage and query processing for database courses.",
    5: "The definitive reference on algorithms: rigorous, complete and widely used for university courses and interview preparation.",
    6: "Core digital signal processing: sampling, transforms, filter design and spectral analysis, with problems for every chapter.",
    7: "A well-loved text on analog and digital electronic circuits, from diodes and transistors to amplifiers and ICs.",
    8: "Covers the full CMOS VLSI design flow, from device physics and logic design to layout and system-level considerations.",
    9: "Analog and digital communication theory explained with practical systems, noise analysis and modulation techniques.",
    10: "Accessible coverage of semiconductor devices and circuit analysis, popular for first and second year electronics courses.",
    11: "Modern power electronics: converters, inverters, drives and control, with design-oriented examples.",
    12: "Machines and transformers explained from first principles, with a strong emphasis on practical operation.",
    13: "Classic control theory: modelling, time and frequency response, stability, and the design of feedback systems.",
    14: "Power flow, fault analysis, stability and system modelling for students of electrical power engineering.",
    15: "Generation, measurement and testing of high voltages, insulation and breakdown, with applications in power systems.",
    16: "Determinate and indeterminate structures taught through clear diagrams and step-by-step worked problems.",
    17: "Soil properties, compaction, bearing capacity and foundation design in one practical, example-driven text.",
    18: "The authoritative text on concrete: its constituents, behaviour, durability and the practice of making it.",
    19: "A standard Indian textbook on surveying and levelling methods, instruments and field procedures.",
    20: "Planning, geometric design, materials and construction of highways with a focus on Indian practice.",
}
