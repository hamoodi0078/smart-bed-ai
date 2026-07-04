"""Prophet stories collection for Islamic education."""

from __future__ import annotations

from typing import Optional


class ProphetStoriesService:
    """Service for accessing stories of the 25 prophets mentioned in the Quran."""

    PROPHETS = [
        {
            "name": "Adam",
            "arabic": "آدم",
            "title": "Father of Mankind",
            "story_summary": "Adam (peace be upon him) was the first human and prophet created by Allah. He was created from clay and given knowledge of all things. When Allah commanded the angels to prostrate to Adam, all obeyed except Iblis (Satan). Adam and his wife Hawwa (Eve) lived in Paradise until they ate from the forbidden tree. After seeking forgiveness, Allah accepted their repentance and sent them to Earth as vicegerents.",
            "key_lessons": [
                "Humans are honored by Allah as His vicegerents on Earth",
                "The importance of repentance and seeking forgiveness",
                "Satan is the eternal enemy of mankind",
                "Knowledge is a divine gift",
            ],
            "mentions_in_quran": ["Al-Baqarah 2:30-39", "Al-A'raf 7:11-25", "Ta-Ha 20:115-123"],
            "age_appropriate": "all",
        },
        {
            "name": "Idris",
            "arabic": "إدريس",
            "title": "The Truthful and Patient",
            "story_summary": "Prophet Idris (Enoch) was known for his truthfulness and patience. He was the first to write with a pen and was raised to a high station by Allah. He called his people to worship Allah alone and abandon idol worship.",
            "key_lessons": [
                "Patience and truthfulness are noble qualities",
                "Knowledge and learning are important in Islam",
                "Steadfastness in calling to the truth",
            ],
            "mentions_in_quran": ["Maryam 19:56-57", "Al-Anbya 21:85"],
            "age_appropriate": "all",
        },
        {
            "name": "Nuh",
            "arabic": "نوح",
            "title": "Noah - The Patient Warner",
            "story_summary": "Prophet Nuh (Noah) preached to his people for 950 years, calling them to abandon idol worship. Despite his patience and persistence, only a small group believed. Allah commanded him to build an ark, and when the great flood came, only the believers were saved. This story teaches about patience, perseverance, and the consequences of rejecting divine guidance.",
            "key_lessons": [
                "Patience in calling to truth, even when rejected",
                "Obedience to Allah's commands",
                "Divine punishment for persistent rejection",
                "Salvation through faith",
            ],
            "mentions_in_quran": ["Nuh 71:1-28", "Hud 11:25-49", "Al-Mu'minun 23:23-30"],
            "age_appropriate": "all",
        },
        {
            "name": "Hud",
            "arabic": "هود",
            "title": "Prophet to the People of 'Ad",
            "story_summary": "Prophet Hud was sent to the people of 'Ad, a powerful nation that built great monuments. They became arrogant and rejected Hud's message. Despite warnings, they persisted in their ways, and Allah destroyed them with a violent wind that lasted seven nights and eight days.",
            "key_lessons": [
                "Arrogance and ingratitude lead to destruction",
                "Material strength cannot save from divine punishment",
                "Importance of humility and gratitude",
            ],
            "mentions_in_quran": ["Hud 11:50-60", "Al-Ahqaf 46:21-26"],
            "age_appropriate": "all",
        },
        {
            "name": "Salih",
            "arabic": "صالح",
            "title": "Prophet to the People of Thamud",
            "story_summary": "Prophet Salih was sent to the Thamud people who carved homes in mountains. When they demanded a miracle, Allah sent a she-camel as a sign. They were warned not to harm her, but they killed her in arrogance. As a result, they were destroyed by a mighty earthquake.",
            "key_lessons": [
                "Signs of Allah should not be violated",
                "Arrogance leads to downfall",
                "Divine warnings should be heeded",
            ],
            "mentions_in_quran": ["Al-A'raf 7:73-79", "Hud 11:61-68", "Ash-Shu'ara 26:141-159"],
            "age_appropriate": "all",
        },
        {
            "name": "Ibrahim",
            "arabic": "إبراهيم",
            "title": "Abraham - The Friend of Allah",
            "story_summary": "Prophet Ibrahim (Abraham) is one of the greatest prophets. He challenged idol worship even as a youth, breaking the idols to prove their powerlessness. He was thrown into fire but Allah saved him. He was tested with sacrificing his son Isma'il, showing perfect submission. He built the Ka'bah with Isma'il and is the father of prophets.",
            "key_lessons": [
                "Unshakeable faith in Allah",
                "Standing for truth against all odds",
                "Complete submission to Allah's will",
                "The reward of patience and trust",
            ],
            "mentions_in_quran": [
                "Al-Baqarah 2:124-141",
                "As-Saffat 37:83-113",
                "Al-Anbya 21:51-73",
            ],
            "age_appropriate": "all",
        },
        {
            "name": "Lut",
            "arabic": "لوط",
            "title": "Lot - Warner Against Immorality",
            "story_summary": "Prophet Lut (Lot) was sent to a people who committed shameful acts of immorality. Despite his warnings, they refused to change. Angels came as guests to Lut, and when his people tried to harm them, Allah saved Lut and his family (except his wife) and destroyed the city.",
            "key_lessons": [
                "Importance of moral purity",
                "Consequences of persisting in sin",
                "Allah protects the righteous",
            ],
            "mentions_in_quran": ["Al-A'raf 7:80-84", "Hud 11:77-83", "Al-Hijr 15:57-77"],
            "age_appropriate": "teen_adult",
        },
        {
            "name": "Isma'il",
            "arabic": "إسماعيل",
            "title": "Ishmael - The Sacrificial Son",
            "story_summary": "Prophet Isma'il was the son of Ibrahim. When very young, he and his mother Hajar were left in the desert of Makkah by Allah's command. Later, Ibrahim saw in a dream that he must sacrifice Isma'il. Both father and son submitted to Allah's will, and at the last moment, Allah replaced Isma'il with a ram. This teaches perfect submission.",
            "key_lessons": [
                "Complete submission to Allah's will",
                "Trust in Allah's plan",
                "Obedience to parents in righteousness",
                "Patience in trials",
            ],
            "mentions_in_quran": ["As-Saffat 37:99-113", "Al-Baqarah 2:127-129"],
            "age_appropriate": "all",
        },
        {
            "name": "Ishaq",
            "arabic": "إسحاق",
            "title": "Isaac - The Blessed Son",
            "story_summary": "Prophet Ishaq (Isaac) was the second son of Ibrahim, born to Sarah in their old age. He was a prophet and the father of Ya'qub (Jacob). Through his lineage came many prophets including 'Isa (Jesus).",
            "key_lessons": [
                "Allah's promises always come true",
                "Blessings can come in unexpected ways",
                "Gratitude for divine gifts",
            ],
            "mentions_in_quran": ["Hud 11:71-73", "As-Saffat 37:112-113"],
            "age_appropriate": "all",
        },
        {
            "name": "Ya'qub",
            "arabic": "يعقوب",
            "title": "Jacob (Israel) - The Patient Father",
            "story_summary": "Prophet Ya'qub (Jacob), also known as Israel, was the son of Ishaq. He is most known for his story with his son Yusuf. When Yusuf was separated from him, Ya'qub showed immense patience and never lost hope in Allah's mercy, maintaining his faith despite years of grief.",
            "key_lessons": [
                "Patience in adversity",
                "Never losing hope in Allah's mercy",
                "Maintaining faith through trials",
                "The blessing of eventual reunion",
            ],
            "mentions_in_quran": ["Yusuf 12:1-111", "Maryam 19:49"],
            "age_appropriate": "all",
        },
        {
            "name": "Yusuf",
            "arabic": "يوسف",
            "title": "Joseph - The Beautiful and Truthful",
            "story_summary": "Prophet Yusuf (Joseph) had a dream that his brothers would bow to him. His jealous brothers threw him in a well. He was sold into slavery in Egypt, falsely accused and imprisoned. Through his ability to interpret dreams, he became the treasurer of Egypt. Years later, his family came seeking food during famine, and his dream came true when they bowed before him. He forgave his brothers, reunited with his father, and all praised Allah.",
            "key_lessons": [
                "Patience and maintaining character through trials",
                "Forgiveness and mercy",
                "Trust in Allah's plan",
                "Dreams can be divine messages",
                "Justice and wisdom in leadership",
            ],
            "mentions_in_quran": ["Yusuf 12:1-111 (entire surah)"],
            "age_appropriate": "all",
        },
        {
            "name": "Ayyub",
            "arabic": "أيوب",
            "title": "Job - The Most Patient",
            "story_summary": "Prophet Ayyub (Job) was a wealthy and blessed man who lost everything - his wealth, children, and health. He was tested with severe illness for years. Despite immense suffering, he never complained and only called upon Allah. Due to his patience, Allah restored his health, doubled his wealth, and blessed him with children again.",
            "key_lessons": [
                "Ultimate patience in the face of trials",
                "Never despairing of Allah's mercy",
                "Maintaining faith through loss",
                "The reward of steadfastness",
                "Trials test and strengthen faith",
            ],
            "mentions_in_quran": ["Al-Anbya 21:83-84", "Sad 38:41-44"],
            "age_appropriate": "all",
        },
        {
            "name": "Shu'ayb",
            "arabic": "شعيب",
            "title": "Jethro - The Eloquent Speaker",
            "story_summary": "Prophet Shu'ayb was sent to the people of Madyan who were cheating in trade, giving less in measure and weight. He called them to worship Allah alone and to deal justly. They rejected him, and Allah destroyed them with punishment.",
            "key_lessons": [
                "Honesty in business dealings",
                "Justice and fairness in transactions",
                "Economic justice is part of faith",
            ],
            "mentions_in_quran": ["Al-A'raf 7:85-93", "Hud 11:84-95"],
            "age_appropriate": "all",
        },
        {
            "name": "Musa",
            "arabic": "موسى",
            "title": "Moses - The One Who Spoke to Allah",
            "story_summary": "Prophet Musa (Moses) was born when Pharaoh was killing newborn boys. His mother placed him in a basket in the river, and he was raised in Pharaoh's palace. As an adult, Allah chose him as a prophet and sent him to free the Children of Israel from Pharaoh's oppression. After many miracles (staff turning to serpent, the ten plagues), Pharaoh let them go but then pursued them. Allah parted the Red Sea for Musa and his people, and drowned Pharaoh's army. Musa received the Torah on Mount Sinai.",
            "key_lessons": [
                "Allah's plan works in mysterious ways",
                "Stand against oppression",
                "Miracles are signs of Allah's power",
                "Patience with one's community",
                "The importance of the law and guidance",
            ],
            "mentions_in_quran": ["Ta-Ha 20:9-98", "Al-Qasas 28:1-46", "Al-A'raf 7:103-162"],
            "age_appropriate": "all",
        },
        {
            "name": "Harun",
            "arabic": "هارون",
            "title": "Aaron - The Assistant Prophet",
            "story_summary": "Prophet Harun (Aaron) was the brother of Musa and was appointed as his helper and prophet. He was eloquent in speech and supported Musa in his mission to Pharaoh. When Musa went to Mount Sinai, Harun was left in charge, but some people began worshipping a golden calf. Harun tried to stop them but faced difficulty.",
            "key_lessons": [
                "Importance of supporting good leadership",
                "Speaking truth with wisdom",
                "Patience in guiding people",
                "Standing against wrong even when difficult",
            ],
            "mentions_in_quran": ["Ta-Ha 20:29-36", "Al-A'raf 7:142-150"],
            "age_appropriate": "all",
        },
        {
            "name": "Dawud",
            "arabic": "داوود",
            "title": "David - The Psalms Singer",
            "story_summary": "Prophet Dawud (David) was blessed with a beautiful voice and was given the Zabur (Psalms). He killed the giant Goliath as a youth with a sling. Allah made him a king and prophet, and he judged with wisdom. Mountains and birds would glorify Allah with him. He was also skilled in making armor.",
            "key_lessons": [
                "Small can defeat large with Allah's help",
                "Wisdom and justice in leadership",
                "Gratitude to Allah through worship",
                "Using skills to serve others",
            ],
            "mentions_in_quran": ["Sad 38:17-26", "Al-Baqarah 2:251", "Saba 34:10-11"],
            "age_appropriate": "all",
        },
        {
            "name": "Sulayman",
            "arabic": "سليمان",
            "title": "Solomon - The Wise King",
            "story_summary": "Prophet Sulayman (Solomon) was the son of Dawud. Allah gave him knowledge, wisdom, and a kingdom unlike any other. He could understand the language of animals and birds, and jinn worked under his command. He built the great temple in Jerusalem. Despite his power, he always attributed everything to Allah and remained humble.",
            "key_lessons": [
                "Gratitude in prosperity",
                "Using power and wealth for good",
                "Humility despite greatness",
                "Wisdom in judgment",
                "All power belongs to Allah",
            ],
            "mentions_in_quran": ["An-Naml 27:15-44", "Saba 34:12-14", "Sad 38:30-40"],
            "age_appropriate": "all",
        },
        {
            "name": "Ilyas",
            "arabic": "إلياس",
            "title": "Elijah - The Steadfast",
            "story_summary": "Prophet Ilyas (Elijah) was sent to the Israelites who were worshipping Baal (a false deity). He called them back to worshipping Allah alone, but most rejected him. Only a few believed and were saved.",
            "key_lessons": [
                "Standing firm against false worship",
                "Courage in calling to truth",
                "Not being discouraged by few followers",
            ],
            "mentions_in_quran": ["As-Saffat 37:123-132"],
            "age_appropriate": "all",
        },
        {
            "name": "Al-Yasa'",
            "arabic": "اليسع",
            "title": "Elisha - The Righteous",
            "story_summary": "Prophet Al-Yasa' (Elisha) succeeded Ilyas and continued calling the Children of Israel to worship Allah alone. He performed miracles and guided his people with patience.",
            "key_lessons": [
                "Continuing the work of predecessors",
                "Patience in da'wah",
                "Righteousness and steadfastness",
            ],
            "mentions_in_quran": ["Al-An'am 6:86", "Sad 38:48"],
            "age_appropriate": "all",
        },
        {
            "name": "Yunus",
            "arabic": "يونس",
            "title": "Jonah - The One Swallowed by the Whale",
            "story_summary": "Prophet Yunus (Jonah) was sent to the people of Nineveh. When they initially rejected him, he left in anger without Allah's permission. He boarded a ship that was caught in a storm. The sailors cast lots, and Yunus was thrown into the sea. A whale swallowed him. In the darkness, he repented and glorified Allah. Allah saved him, and he returned to his people who had turned to Allah and were saved from punishment.",
            "key_lessons": [
                "Patience with Allah's plan",
                "The power of sincere repentance",
                "Allah accepts those who turn to Him",
                "Never give up on people's ability to change",
                "Glorifying Allah in times of distress",
            ],
            "mentions_in_quran": ["Yunus 10:98", "Al-Anbya 21:87-88", "As-Saffat 37:139-148"],
            "age_appropriate": "all",
        },
        {
            "name": "Zakariya",
            "arabic": "زكريا",
            "title": "Zachariah - The Praying Elder",
            "story_summary": "Prophet Zakariya (Zachariah) was an elderly man who had no children. He took care of Maryam (Mary) and saw her receive provisions miraculously. Inspired, he prayed to Allah for a righteous child despite his old age and his wife's barrenness. Allah answered his prayer and blessed him with Yahya (John).",
            "key_lessons": [
                "Never too late to pray to Allah",
                "Allah answers prayers in His way and time",
                "Caring for orphans is blessed",
                "Faith in Allah's power over nature",
            ],
            "mentions_in_quran": ["Maryam 19:1-11", "Ali 'Imran 3:37-41"],
            "age_appropriate": "all",
        },
        {
            "name": "Yahya",
            "arabic": "يحيى",
            "title": "John the Baptist - The Honored Youth",
            "story_summary": "Prophet Yahya (John) was born to elderly parents through a miracle. From childhood, he was given wisdom, knowledge, and prophethood. He was known for his piety, kindness to his parents, and his strong stance for truth. He called people to prepare for the coming of 'Isa (Jesus).",
            "key_lessons": [
                "Piety from a young age",
                "Kindness to parents",
                "Standing for truth fearlessly",
                "Youth can be righteous leaders",
            ],
            "mentions_in_quran": ["Maryam 19:12-15", "Ali 'Imran 3:39"],
            "age_appropriate": "all",
        },
        {
            "name": "'Isa",
            "arabic": "عيسى",
            "title": "Jesus - The Messiah",
            "story_summary": "Prophet 'Isa (Jesus) was born miraculously to Maryam (Mary) without a father. He spoke from the cradle defending his mother's honor. Allah gave him many miracles: healing the sick, giving sight to the blind, and bringing the dead to life by Allah's permission. He received the Injil (Gospel). He preached the worship of Allah alone. When enemies plotted to crucify him, Allah raised him to the heavens. He will return before the Day of Judgment.",
            "key_lessons": [
                "Allah's power over all creation",
                "Miracles are signs, not objects of worship",
                "Worship Allah alone, not His prophets",
                "Patience in the face of rejection",
                "The truth will always prevail",
            ],
            "mentions_in_quran": ["Maryam 19:16-36", "Ali 'Imran 3:45-55", "Al-Ma'idah 5:110-120"],
            "age_appropriate": "all",
        },
        {
            "name": "Muhammad",
            "arabic": "محمد",
            "title": "The Final Messenger - Peace be upon him",
            "story_summary": "Prophet Muhammad ﷺ was born in Makkah in 570 CE. Known for his truthfulness and trustworthiness, he received the first revelation at age 40 in the Cave of Hira. For 23 years, he called people to Islam, facing severe persecution in Makkah. He migrated to Madinah, established an Islamic state, and eventually returned to Makkah victorious. He is the final prophet, and the Quran was revealed to him. His life is the perfect example for all humanity.",
            "key_lessons": [
                "Perfection of character and conduct",
                "Patience in adversity",
                "Mercy to all creation",
                "Justice and equality",
                "The Quran is the final revelation",
                "Following the Sunnah",
                "Compassion and forgiveness",
            ],
            "mentions_in_quran": ["Al-Ahzab 33:40", "Muhammad 47:1-38", "Al-Fath 48:29"],
            "age_appropriate": "all",
        },
        {
            "name": "Dhul-Kifl",
            "arabic": "ذو الكفل",
            "title": "The Patient One",
            "story_summary": "Prophet Dhul-Kifl is briefly mentioned in the Quran. He was known for his patience and righteousness. Some scholars say he was patient in prayer and fasting, maintaining his worship consistently.",
            "key_lessons": ["Consistency in worship", "Patience in obedience", "Righteousness"],
            "mentions_in_quran": ["Al-Anbya 21:85", "Sad 38:48"],
            "age_appropriate": "all",
        },
    ]

    def get_all_prophets(self) -> list[dict]:
        """Get list of all 25 prophets."""
        return self.PROPHETS

    def get_prophet_by_name(self, name: str) -> Optional[dict]:
        """Get a specific prophet's story by name."""
        name_lower = name.lower()
        for prophet in self.PROPHETS:
            if (
                prophet["name"].lower() == name_lower
                or prophet["arabic"] == name
                or name_lower in prophet["name"].lower()
            ):
                return prophet
        return None

    def get_prophets_by_age_group(self, age_group: str = "all") -> list[dict]:
        """
        Filter prophets by age appropriateness.

        Args:
            age_group: 'all', 'children', 'teen_adult'
        """
        if age_group == "all":
            return self.PROPHETS

        return [
            p
            for p in self.PROPHETS
            if p["age_appropriate"] == age_group or p["age_appropriate"] == "all"
        ]

    def search_stories(self, query: str) -> list[dict]:
        """Search prophet stories by keyword."""
        query_lower = query.lower()
        results = []

        for prophet in self.PROPHETS:
            if (
                query_lower in prophet["name"].lower()
                or query_lower in prophet["title"].lower()
                or query_lower in prophet["story_summary"].lower()
                or any(query_lower in lesson.lower() for lesson in prophet["key_lessons"])
            ):
                results.append(prophet)

        return results
