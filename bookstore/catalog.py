"""Seed catalogue: departments, coupons and books.

Titles, authors and publishers are real. Prices, stock and ratings are demo values.
ISBNs are only filled in where they are well known; books without one get a generated cover
(upload a real cover in Admin > Books). Where an ISBN is present the cover is loaded from
Open Library in the browser and falls back to the generated cover if it isn't found.
"""

# slug, name, group, sort order
CATEGORIES = [
    ("cse", "Computer Science", "Engineering", 1),
    ("ece", "Electronics", "Engineering", 2),
    ("eee", "Electrical", "Engineering", 3),
    ("mech", "Mechanical", "Engineering", 4),
    ("civil", "Civil Engineering", "Engineering", 5),
    ("maths", "Mathematics", "Science & Maths", 6),
    ("science", "Physics & Chemistry", "Science & Maths", 7),
    ("mgmt", "Management & Economics", "Business & Finance", 8),
    ("biz", "Business & Investing", "Business & Finance", 9),
    ("exams", "Competitive Exams", "Exam Prep", 10),
    ("fiction", "Fiction & Classics", "Fiction", 11),
    ("indian", "Indian Writing", "Fiction", 12),
    ("selfhelp", "Self-Help", "Non-Fiction", 13),
    ("bio", "Biography & History", "Non-Fiction", 14),
    ("kids", "Children's Books", "Kids", 15),
]

# code, percent, minimum cart value, max discount
COUPONS = [
    ("WELCOME10", 10, 300, 150),
    ("BOOKS20", 20, 1000, 400),
    ("STUDENT5", 5, 0, 100),
]

# title, subtitle, button text, link, theme, category whose covers appear on the banner
BANNERS = [
    ("Back to campus, up to 25% off", "Core engineering textbooks from Pearson, McGraw Hill and Wiley, delivered fast.",
     "Shop engineering", "/books?group=Engineering&sort=discount", "indigo", "cse"),
    ("Crack your next exam", "Aptitude, reasoning, polity and English guides that toppers actually use.",
     "Browse exam prep", "/books?category=exams", "violet", "exams"),
    ("Fresh reads under Rs 399", "Novels, classics and bestsellers for the next time you need a break from studying.",
     "Find your next read", "/books?group=Fiction&max_price=399", "amber", "fiction"),
]

# The original 20 books keep their ids (1-20) and data from the first version of the project.
ORIGINAL_DESCRIPTIONS = {
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
ORIGINAL_CATEGORY_SLUG = {"cse": "cse", "ece": "ece", "eee": "eee", "civil": "civil"}

# category, title, author, publisher, price (Rs), rating, description, isbn, language
H = "Hindi"
NEW_BOOKS = [
    # ---- Computer Science
    ("cse", "Clean Code", "Robert C. Martin", "Pearson", 520, 4.7, "A handbook of agile software craftsmanship: how to write readable, maintainable code and spot the smells that need fixing.", "9780132350884"),
    ("cse", "The Pragmatic Programmer", "David Thomas, Andrew Hunt", "Addison-Wesley", 640, 4.8, "Practical habits and tips for becoming a better developer, from debugging to design and career growth.", "9780135957059"),
    ("cse", "Design Patterns", "Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides", "Addison-Wesley", 590, 4.6, "The classic catalogue of 23 reusable object-oriented design patterns by the 'Gang of Four'.", "9780201633610"),
    ("cse", "The C Programming Language", "Brian W. Kernighan, Dennis M. Ritchie", "Pearson", 450, 4.7, "The compact, definitive guide to C, written by the language's creators.", "9780131103627"),
    ("cse", "Let Us C", "Yashavant Kanetkar", "BPB Publications", 380, 4.4, "A beginner-friendly Indian favourite for learning C programming step by step.", None),
    ("cse", "Cracking the Coding Interview", "Gayle Laakmann McDowell", "CareerCup", 780, 4.7, "189 programming questions and solutions, plus the strategy behind technical interviews at top companies.", "9780984782857"),
    ("cse", "Artificial Intelligence: A Modern Approach", "Stuart Russell, Peter Norvig", "Pearson", 850, 4.7, "The most widely used AI textbook, covering search, logic, planning, learning and probabilistic reasoning.", "9780136042594"),
    ("cse", "Compilers: Principles, Techniques, and Tools", "Alfred Aho, Monica Lam, Ravi Sethi, Jeffrey Ullman", "Pearson", 690, 4.5, "The 'dragon book': lexical analysis, parsing, code generation and optimisation.", "9780321486813"),
    ("cse", "Effective Java", "Joshua Bloch", "Addison-Wesley", 680, 4.8, "90 best practices for writing clear, correct and robust Java code.", "9780134685991"),
    ("cse", "Computer Organization and Architecture", "William Stallings", "Pearson", 590, 4.4, "Designing for performance: processors, memory hierarchy, I/O and parallel organisation.", None),
    ("cse", "Computer Networking: A Top-Down Approach", "James Kurose, Keith Ross", "Pearson", 660, 4.6, "Networking taught from the application layer down, with a strong focus on the Internet.", None),
    ("cse", "Introduction to the Theory of Computation", "Michael Sipser", "Cengage", 540, 4.6, "Automata, computability and complexity explained with unusual clarity.", None),
    ("cse", "Hands-On Machine Learning with Scikit-Learn, Keras & TensorFlow", "Aurelien Geron", "O'Reilly", 1450, 4.8, "A practical, code-first route into machine learning and deep learning.", None),
    # ---- Electronics
    ("ece", "Signals and Systems", "Alan V. Oppenheim, Alan S. Willsky", "Pearson", 620, 4.5, "Continuous and discrete-time signals, Fourier and Laplace transforms and system analysis.", None),
    ("ece", "Digital Design", "M. Morris Mano", "Pearson", 520, 4.6, "Logic design, combinational and sequential circuits and an introduction to HDL.", None),
    ("ece", "Microprocessor Architecture, Programming and Applications with the 8085", "Ramesh Gaonkar", "Penram", 450, 4.4, "The standard introduction to the 8085, its instruction set and interfacing.", None),
    ("ece", "Elements of Electromagnetics", "Matthew N. O. Sadiku", "Oxford", 640, 4.4, "Vector analysis, static fields, Maxwell's equations and wave propagation.", None),
    ("ece", "Network Analysis", "M. E. Van Valkenburg", "Pearson", 420, 4.5, "A classic on circuit theorems, transient analysis and network functions.", None),
    ("ece", "Op-Amps and Linear Integrated Circuits", "Ramakant Gayakwad", "Pearson", 480, 4.5, "Operational amplifiers, filters, timers and converters with practical circuit examples.", None),
    # ---- Electrical
    ("eee", "Electrical Machines", "P. S. Bimbhra", "Khanna Publishers", 520, 4.5, "DC machines, transformers, induction and synchronous machines for undergraduate courses.", None),
    ("eee", "Fundamentals of Electric Circuits", "Charles Alexander, Matthew Sadiku", "McGraw Hill", 640, 4.5, "A problem-driven introduction to circuit analysis, with a rich set of worked examples.", None),
    ("eee", "Principles of Power Systems", "V. K. Mehta, Rohit Mehta", "S. Chand", 480, 4.4, "Generation, transmission, distribution and protection explained for electrical students.", None),
    ("eee", "A Textbook of Electrical Technology", "B. L. Theraja", "S. Chand", 720, 4.6, "A comprehensive multi-volume reference on electrical engineering fundamentals.", None),
    # ---- Mechanical
    ("mech", "Engineering Thermodynamics", "P. K. Nag", "McGraw Hill", 590, 4.5, "Laws of thermodynamics, cycles, entropy and properties of pure substances.", None),
    ("mech", "Fluid Mechanics and Hydraulic Machines", "R. K. Bansal", "Laxmi Publications", 520, 4.5, "Fluid properties, flow analysis, turbines and pumps with many solved problems.", None),
    ("mech", "Theory of Machines", "S. S. Rattan", "McGraw Hill", 540, 4.3, "Kinematics and dynamics of mechanisms, gears, cams, governors and balancing.", None),
    ("mech", "A Textbook of Machine Design", "R. S. Khurmi, J. K. Gupta", "S. Chand", 580, 4.5, "Design of shafts, joints, springs, bearings and other machine elements.", None),
    ("mech", "Heat and Mass Transfer", "Yunus A. Cengel", "McGraw Hill", 720, 4.5, "Conduction, convection, radiation and mass transfer with a practical engineering focus.", None),
    ("mech", "Vector Mechanics for Engineers: Statics and Dynamics", "Ferdinand Beer, E. Russell Johnston", "McGraw Hill", 690, 4.4, "A rigorous treatment of statics and dynamics with a vector approach.", None),
    ("mech", "Manufacturing Engineering and Technology", "Serope Kalpakjian, Steven Schmid", "Pearson", 760, 4.4, "Casting, forming, machining, joining and modern manufacturing processes.", None),
    ("mech", "Mechanics of Materials", "R. C. Hibbeler", "Pearson", 650, 4.5, "Stress, strain, torsion, bending and deflection, with clear figures and examples.", None),
    ("mech", "Strength of Materials", "R. K. Rajput", "S. Chand", 480, 4.2, "Simple and compound stresses, beams, columns and strain energy for degree courses.", None),
    # ---- Civil
    ("civil", "Soil Mechanics and Foundations", "B. C. Punmia", "Laxmi Publications", 560, 4.4, "Soil classification, permeability, consolidation, shear strength and foundations.", None),
    ("civil", "Reinforced Concrete Design", "S. Unnikrishna Pillai, Devdas Menon", "McGraw Hill", 640, 4.5, "Limit state design of beams, slabs, columns and footings as per Indian codes.", None),
    ("civil", "Environmental Engineering", "Howard Peavy, Donald Rowe, George Tchobanoglous", "McGraw Hill", 590, 4.3, "Water supply, wastewater treatment, air pollution and solid waste management.", None),
    ("civil", "Building Construction", "B. C. Punmia", "Laxmi Publications", 450, 4.3, "Materials, masonry, floors, roofs and finishing in building construction.", None),
    # ---- Mathematics
    ("maths", "Higher Engineering Mathematics", "B. S. Grewal", "Khanna Publishers", 520, 4.5, "The standard Indian text for engineering mathematics, with a vast set of exercises.", None),
    ("maths", "Advanced Engineering Mathematics", "Erwin Kreyszig", "Wiley", 640, 4.6, "Differential equations, linear algebra, vector calculus and complex analysis for engineers.", None),
    ("maths", "Calculus: Early Transcendentals", "James Stewart", "Cengage", 780, 4.5, "A clear and well-illustrated calculus course with plenty of real-world applications.", None),
    ("maths", "Introduction to Linear Algebra", "Gilbert Strang", "Wellesley-Cambridge Press", 720, 4.7, "Linear algebra taught through geometry and applications by the MIT professor.", None),
    ("maths", "A First Course in Probability", "Sheldon Ross", "Pearson", 560, 4.6, "A lively introduction to probability with hundreds of examples and exercises.", None),
    ("maths", "Discrete Mathematics and Its Applications", "Kenneth H. Rosen", "McGraw Hill", 640, 4.5, "Logic, sets, combinatorics, graphs and proofs for computer science students.", None),
    ("maths", "Thomas' Calculus", "George B. Thomas", "Pearson", 700, 4.5, "A rigorous and widely adopted calculus text with applications in science and engineering.", None),
    ("maths", "Concrete Mathematics", "Ronald Graham, Donald Knuth, Oren Patashnik", "Addison-Wesley", 820, 4.7, "The mathematics behind computer science: sums, recurrences, number theory and generating functions.", "9780201558029"),
    ("maths", "Numerical Methods for Engineers", "Steven Chapra, Raymond Canale", "McGraw Hill", 640, 4.4, "Numerical techniques for roots, equations, integration and differential equations.", None),
    # ---- Physics & Chemistry
    ("science", "Concepts of Physics, Volume 1", "H. C. Verma", "Bharati Bhawan", 380, 4.8, "India's favourite physics text for JEE and board exams: mechanics, waves and thermodynamics.", None),
    ("science", "Concepts of Physics, Volume 2", "H. C. Verma", "Bharati Bhawan", 350, 4.8, "Electricity, magnetism, optics and modern physics with exceptional problem sets.", None),
    ("science", "Fundamentals of Physics", "David Halliday, Robert Resnick, Jearl Walker", "Wiley", 750, 4.6, "A comprehensive university physics course with clear explanations and diagrams.", None),
    ("science", "Physical Chemistry", "Peter Atkins, Julio de Paula", "Oxford", 720, 4.5, "Thermodynamics, kinetics and quantum chemistry in a modern, accessible presentation.", None),
    ("science", "Organic Chemistry", "Robert Morrison, Robert Boyd", "Pearson", 640, 4.5, "A long-standing standard for understanding organic reactions and mechanisms.", None),
    ("science", "Concise Inorganic Chemistry", "J. D. Lee", "Wiley", 560, 4.6, "Periodic trends, bonding, coordination chemistry and descriptive inorganic chemistry.", None),
    ("science", "A Brief History of Time", "Stephen Hawking", "Bantam", 399, 4.6, "From the Big Bang to black holes, a landmark of popular science.", "9780553380163"),
    ("science", "Cosmos", "Carl Sagan", "Ballantine", 450, 4.7, "A sweeping journey through the universe and the history of scientific discovery.", "9780345539434"),
    ("science", "Surely You're Joking, Mr. Feynman!", "Richard P. Feynman", "W. W. Norton", 450, 4.6, "Adventures of a curious character, told by the Nobel-winning physicist himself.", "9780393316049"),
    ("science", "Astrophysics for People in a Hurry", "Neil deGrasse Tyson", "W. W. Norton", 350, 4.5, "The universe's biggest ideas in a book you can read in an evening.", "9780393609394"),
    # ---- Management & Economics
    ("mgmt", "Marketing Management", "Philip Kotler, Kevin Lane Keller", "Pearson", 620, 4.5, "The leading text on modern marketing strategy, branding and customer relationships.", None),
    ("mgmt", "Financial Management", "I. M. Pandey", "Vikas Publishing", 580, 4.4, "Investment, financing and dividend decisions explained with Indian examples.", None),
    ("mgmt", "Principles of Economics", "N. Gregory Mankiw", "Cengage", 640, 4.5, "A clear introduction to micro and macroeconomics built around real-world questions.", None),
    ("mgmt", "Organizational Behavior", "Stephen P. Robbins, Timothy Judge", "Pearson", 540, 4.4, "How individuals and groups behave in organisations, with cases and self-assessments.", None),
    ("mgmt", "Indian Economy", "Ramesh Singh", "McGraw Hill", 540, 4.4, "A complete guide to the Indian economy for students and civil services aspirants.", None),
    ("mgmt", "Principles of Management", "P. C. Tripathi, P. N. Reddy", "McGraw Hill", 480, 4.3, "Planning, organising, leading and controlling, with Indian business cases.", None),
    # ---- Business & Investing
    ("biz", "The Intelligent Investor", "Benjamin Graham", "HarperBusiness", 499, 4.7, "The timeless guide to value investing and keeping emotion out of your decisions.", "9780060555665"),
    ("biz", "Rich Dad Poor Dad", "Robert T. Kiyosaki", "Plata Publishing", 350, 4.5, "Personal finance lessons on assets, liabilities and building wealth.", "9781612680194"),
    ("biz", "The Psychology of Money", "Morgan Housel", "Harriman House", 299, 4.7, "Timeless lessons on how behaviour, not intelligence, shapes our financial outcomes.", "9780857197689"),
    ("biz", "Zero to One", "Peter Thiel, Blake Masters", "Crown Business", 399, 4.5, "Notes on startups and how to build companies that create the future.", "9780804139298"),
    ("biz", "The Lean Startup", "Eric Ries", "Currency", 450, 4.5, "A scientific, iterative approach to building products people actually want.", "9780307887894"),
    ("biz", "Good to Great", "Jim Collins", "HarperBusiness", 499, 4.5, "Why some companies make the leap to lasting greatness and others don't.", "9780066620992"),
    ("biz", "Start with Why", "Simon Sinek", "Portfolio", 399, 4.5, "How great leaders inspire action by starting with purpose.", "9781591846444"),
    # ---- Competitive Exams
    ("exams", "Quantitative Aptitude for Competitive Examinations", "R. S. Aggarwal", "S. Chand", 450, 4.5, "Thousands of solved and practice problems for banking, SSC and other exams.", None),
    ("exams", "A Modern Approach to Verbal & Non-Verbal Reasoning", "R. S. Aggarwal", "S. Chand", 420, 4.5, "Reasoning topics with shortcuts, solved examples and practice sets.", None),
    ("exams", "Indian Polity", "M. Laxmikanth", "McGraw Hill", 620, 4.7, "The go-to book on the Constitution and political system for UPSC preparation.", None),
    ("exams", "Objective General English", "S. P. Bakshi", "Arihant", 350, 4.4, "Grammar, vocabulary and comprehension practice for competitive exams.", None),
    ("exams", "Word Power Made Easy", "Norman Lewis", "Goyal Publishers", 280, 4.6, "A step-by-step method to build a powerful vocabulary.", None),
    ("exams", "High School English Grammar and Composition", "P. C. Wren, H. Martin", "S. Chand", 320, 4.6, "The evergreen reference for English grammar and writing.", None),
    ("exams", "Fast Track Objective Arithmetic", "Rajesh Verma", "Arihant", 340, 4.4, "Shortcut techniques and practice for arithmetic in competitive exams.", None),
    ("exams", "A Brief History of Modern India", "Rajiv Ahir", "Spectrum Books", 380, 4.5, "A concise, exam-focused account of modern Indian history.", None),
    ("exams", "India's Struggle for Independence", "Bipan Chandra", "Penguin India", 380, 4.6, "The definitive history of the Indian freedom movement.", None),
    ("exams", "Indian Economy for Civil Services", "Nitin Singhania", "McGraw Hill", 560, 4.5, "Concepts, schemes and current developments in the Indian economy.", None),
    ("exams", "Lucent's General Knowledge", "Binay Karna", "Lucent Publication", 280, 4.4, "A compact general knowledge guide for competitive exams.", None),
    # ---- Fiction & Classics
    ("fiction", "The Alchemist", "Paulo Coelho", "HarperOne", 299, 4.6, "A shepherd's journey to find treasure becomes a fable about following your dreams.", "9780062315007"),
    ("fiction", "1984", "George Orwell", "Signet Classics", 199, 4.7, "A chilling vision of surveillance, propaganda and the loss of truth.", "9780451524935"),
    ("fiction", "Animal Farm", "George Orwell", "Signet Classics", 149, 4.6, "A short, sharp satire of power and revolution told through a farmyard.", "9780451526342"),
    ("fiction", "To Kill a Mockingbird", "Harper Lee", "Harper Perennial", 350, 4.7, "A young girl watches her father defend an innocent man in the American South.", None),
    ("fiction", "Harry Potter and the Philosopher's Stone", "J. K. Rowling", "Bloomsbury", 399, 4.9, "The first adventure of a boy wizard at Hogwarts.", "9780747532743"),
    ("fiction", "The Hobbit", "J. R. R. Tolkien", "HarperCollins", 399, 4.8, "Bilbo Baggins joins a company of dwarves on a quest for dragon-guarded treasure.", None),
    ("fiction", "Pride and Prejudice", "Jane Austen", "Penguin Classics", 199, 4.6, "Wit, manners and romance in Regency England.", "9780141439518"),
    ("fiction", "The Great Gatsby", "F. Scott Fitzgerald", "Scribner", 249, 4.4, "Jazz Age glamour and obsession on Long Island.", "9780743273565"),
    ("fiction", "The Kite Runner", "Khaled Hosseini", "Bloomsbury", 399, 4.6, "A story of friendship, betrayal and redemption set in Afghanistan.", None),
    ("fiction", "The Book Thief", "Markus Zusak", "Black Swan", 399, 4.7, "Narrated by Death, the story of a girl who steals books in Nazi Germany.", None),
    ("fiction", "It Ends with Us", "Colleen Hoover", "Simon & Schuster", 399, 4.4, "A moving and honest novel about love, resilience and difficult choices.", "9781501110368"),
    ("fiction", "The Silent Patient", "Alex Michaelides", "Celadon Books", 399, 4.3, "A psychological thriller about a woman who stops speaking after a shocking crime.", None),
    # ---- Indian Writing
    ("indian", "The God of Small Things", "Arundhati Roy", "Penguin India", 399, 4.3, "A family's tragedy in Kerala, told in lyrical, non-linear prose.", None),
    ("indian", "The White Tiger", "Aravind Adiga", "Atlantic Books", 399, 4.2, "A darkly funny tale of ambition and class in modern India.", None),
    ("indian", "Five Point Someone", "Chetan Bhagat", "Rupa Publications", 175, 4.1, "Three friends navigate life at the IIT campus.", "9788129104595"),
    ("indian", "The Immortals of Meluha", "Amish Tripathi", "Westland", 299, 4.4, "The first book of the Shiva Trilogy, a myth reimagined as an adventure.", None),
    ("indian", "Malgudi Days", "R. K. Narayan", "Indian Thought Publications", 250, 4.7, "Gentle, humorous stories of life in the fictional South Indian town of Malgudi.", None),
    ("indian", "Gunahon Ka Devta", "Dharamvir Bharati", "Bharatiya Jnanpith", 275, 4.6, "A landmark Hindi novel of love, sacrifice and social convention.", None, H),
    ("indian", "Rashmirathi", "Ramdhari Singh Dinkar", "Lokbharti Prakashan", 175, 4.7, "Dinkar's epic poem on Karna, one of the great voices of Hindi poetry.", None, H),
    # ---- Self-Help
    ("selfhelp", "Atomic Habits", "James Clear", "Random House Business", 499, 4.8, "An easy, proven way to build good habits and break bad ones.", "9781847941831"),
    ("selfhelp", "Deep Work", "Cal Newport", "Piatkus", 399, 4.5, "Rules for focused success in a distracted world.", None),
    ("selfhelp", "Ikigai", "Hector Garcia, Francesc Miralles", "Penguin Life", 350, 4.4, "The Japanese secret to a long and happy life.", "9780143130727"),
    ("selfhelp", "Think and Grow Rich", "Napoleon Hill", "TarcherPerigee", 199, 4.5, "A classic on the mindset and principles behind personal achievement.", "9781585424337"),
    ("selfhelp", "How to Win Friends and Influence People", "Dale Carnegie", "Pocket Books", 299, 4.6, "Timeless advice on communication and building relationships.", "9780671027032"),
    ("selfhelp", "The 7 Habits of Highly Effective People", "Stephen R. Covey", "Simon & Schuster", 399, 4.6, "Powerful lessons in personal change and effectiveness.", None),
    ("selfhelp", "The Subtle Art of Not Giving a F*ck", "Mark Manson", "HarperOne", 399, 4.3, "A counterintuitive approach to living a good life.", "9780062457714"),
    ("selfhelp", "Can't Hurt Me", "David Goggins", "Lioncrest Publishing", 599, 4.7, "Master your mind and defy the odds, from a former Navy SEAL.", "9781544512280"),
    ("selfhelp", "Mindset", "Carol S. Dweck", "Ballantine", 399, 4.5, "How a growth mindset changes the way you learn, work and live.", "9780345472328"),
    ("selfhelp", "The Power of Your Subconscious Mind", "Joseph Murphy", "Diamond Books", 199, 4.5, "A bestselling guide to using the power of belief and positive thinking.", None),
    # ---- Biography & History
    ("bio", "Wings of Fire", "A. P. J. Abdul Kalam, Arun Tiwari", "Universities Press", 250, 4.8, "The autobiography of India's Missile Man and former President.", "9788173711466"),
    ("bio", "Ignited Minds", "A. P. J. Abdul Kalam", "Penguin India", 250, 4.6, "Dr Kalam's call to unleash the power within India.", None),
    ("bio", "My Experiments with Truth", "M. K. Gandhi", "Navajivan Trust", 199, 4.6, "Gandhi's own account of his life and the evolution of his ideas.", None),
    ("bio", "The Discovery of India", "Jawaharlal Nehru", "Penguin India", 399, 4.4, "Nehru's reflection on India's history, culture and philosophy.", None),
    ("bio", "Sapiens: A Brief History of Humankind", "Yuval Noah Harari", "Harper", 499, 4.6, "How Homo sapiens came to dominate the planet.", "9780062316097"),
    ("bio", "Homo Deus", "Yuval Noah Harari", "Harper", 499, 4.4, "A brief history of tomorrow, and what humanity may become.", "9780062464316"),
    ("bio", "Steve Jobs", "Walter Isaacson", "Simon & Schuster", 599, 4.6, "The authorised biography based on over forty interviews with Jobs.", "9781451648539"),
    ("bio", "The Diary of a Young Girl", "Anne Frank", "Bantam", 250, 4.7, "The wartime diary of a Jewish girl in hiding.", "9780553296983"),
    ("bio", "Guns, Germs, and Steel", "Jared Diamond", "W. W. Norton", 499, 4.5, "Why some societies advanced faster than others.", "9780393317558"),
    # ---- Children's Books
    ("kids", "Diary of a Wimpy Kid", "Jeff Kinney", "Amulet Books", 399, 4.6, "Greg Heffley's hilarious first year of middle school.", "9780810993136"),
    ("kids", "Matilda", "Roald Dahl", "Puffin", 299, 4.8, "A brilliant girl with magical powers takes on a dreadful headmistress.", "9780142410370"),
    ("kids", "Charlie and the Chocolate Factory", "Roald Dahl", "Puffin", 299, 4.8, "Charlie wins a golden ticket to Willy Wonka's extraordinary factory.", "9780142410318"),
    ("kids", "The Little Prince", "Antoine de Saint-Exupery", "Harcourt", 250, 4.7, "A pilot meets a young prince from another planet in this gentle fable.", "9780156012195"),
    ("kids", "Charlotte's Web", "E. B. White", "HarperCollins", 299, 4.7, "A spider and a pig form an unforgettable friendship.", "9780064400558"),
    ("kids", "Wonder", "R. J. Palacio", "Knopf", 399, 4.8, "Auggie Pullman starts school and teaches everyone about kindness.", "9780375869020"),
    ("kids", "Percy Jackson and the Lightning Thief", "Rick Riordan", "Puffin", 399, 4.7, "A boy discovers he is the son of a Greek god.", None),
    ("kids", "Panchatantra Stories", "Vishnu Sharma", "Penguin India", 199, 4.5, "Classic animal fables with timeless lessons about wisdom and friendship.", None),
]
