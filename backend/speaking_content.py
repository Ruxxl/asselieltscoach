"""Контент Speaking из документа преподавателя «Assel IELTS» (лист «ТЕМЫ SPEAKING»).

Формат намеренно текстовый — как в документе, чтобы новые темы можно было просто вставлять:
- PART1_TEXT: секции "## permanent|new|other", темы разделены пустой строкой, первая строка — название,
  остальные — вопросы.
- PART23_TEXT: записи разделены строкой "====": название, карточка Part 2 (до строки "---"), затем
  вопросы Part 3 (по одному на строку).
Парсинг — parse_part1() / parse_part23(); в базу темы кладёт seed_speaking_topics (backend/seed_data.py).

Правки при переносе (дубли в документе): "Teachers" встречался дважды — вопросы объединены;
"Enjoyable evening" и "New skill" — по две записи, оставлена полная версия; "Place you would like to
visit in your free time" — одинаковая запись повторялась, оставлена одна. В конце вопроса про
торговые центры в документе обрыв ("...so popular in") — дописано "your country?".
"""

PART1_TEXT = """
## permanent

Work/Studies
Do you work or are you a student?
Why did you choose this kind of work/to study this subject?
Do you like your job?
What’s the most interesting part of being a ... (... / student)?
What’s the most difficult part of being a ... (... / student)?
What do you dislike about your work or studies?
What kind of work would you like to do in the future?

Accommodation
Do you live in a house or an apartment/flat?
Can you describe the place where you live?
What do you like about your flat?
Which is your favourite room in your home?
What can you see from the windows?
Would you change anything about your home?
Would you like to move to a different home in the future?

Hometown/city
Tell me about your hometown.
What’s your hometown known for?
Do you like your hometown?
How long have you been living there?
Do you think you’ll continue living there for a long time?
How has your town changed in the last 20 years?

Your Country
Where is your country located?
Which part of your country do most people live in?
What are the main industries in your country?
What are some of the good things about living in your country?
What are some of the bad things about living in your country?
Will you stay in your country in the future?

## new

Paper
Do you carry paper and pens with you when you go out?
Do people still keep handwritten letters today?
Do you still write physical letters?
What did you like to do with paper as a child?
Have you made any crafts with paper?

Secondary school
Do you remember your first day at secondary school?
Is there anything you miss about your secondary school?
What was your favourite subject at secondary school?
Were there any subjects that you found difficult at secondary school?

Fruit and vegetables
What kind of fruits and vegetables do you like?
How often do you eat fruit and vegetables?
What kind of fruits and vegetables do you dislike?
Were there any kind of fruits and vegetables you disliked as a child?
Where do you usually buy fruit and vegetables?

Being punctual
Are you a punctual person?
Do you think being on time is important?
How do you feel when others are late?
How do you remind yourself to be on time?
Why are some people usually late?

Older people
Do you often talk to older people?
Who do you usually talk to among older people?
What do you usually talk about with older people?

Relatives
Do you enjoy spending time with your relatives?
How often do you visit your relatives?
What do you usually do during your visit?
When was the last time you visited them?
Do you prefer to visit your relatives or friends?

Opportunities
Should people try as many different things as they can?
Did you have any opportunities to take part in new activities as a child?

Feeling bored
Do you often feel bored?
When would you feel bored?
What do you do when you feel bored?
Do you think childhood or adulthood is boring?

Politeness
Are you polite?
Have people become less or more polite over time?
Do you think being polite is very important?
How did you learn to be polite as a child?
Who taught you to be polite?
Do you think people should be polite?

Tiredness
Do you often feel tired?
What do you do when you feel tired?
When would you feel tired?
Do you think you get enough rest?

Rubbish and recycling
How do you usually deal with your household garbage?
How do you recycle things like paper and plastic?
Do you sort your garbage before throwing it away?
What do you do when you see rubbish on the street?
Did you learn about recycling when you were a child?

Emails
Do you often send emails?
Is sending emails widespread in your country?
Do you think emails will be more or less common in the future?
How often do you write emails or cards?
Do you prefer texting or emails?

Computers/tablets
Do you like using a computer or tablet?
When would you use a computer or tablet?
When was the first time you used a computer or tablet?
What would your life be like without computers or tablets?
When would it be difficult for you to use a computer or tablet?

Collecting things
Do you collect things?
Are there any things you have kept from your childhood?
Where do you usually keep things you need?
Would you keep old things for a long time? Why?

Lost and found
Have you ever lost things?
Have you ever lost your keys?
Will you post on social media if you lose your item?
What will you do if you find something lost by others?
Will you report it to the police?

Getting lost
Have you ever lost your way?
How can you find your way when you are lost?
Can you read a map when you get lost?
Have you ever helped someone who got lost?

Street market
Are there many street markets in your country?
When was the last time you went to a street market?
Do you prefer shopping in the shopping mall or at the street market?
What do you usually buy at the street market?

Travelling
Do you like travelling long distance?
Did you have a long journey with your family as a child?
Would you like to travel long distance more often in the future?
Do you prefer to sit by the window when travelling?

Advertisements
Do you like advertisements?
What kind of advertising do you like?
Do you often see advertisements when you are on your phone or computer?
Do you see a lot of advertising on trains or other transport?
Is there an advertisement that made an impression on you when you were a child?
Have you ever bought something because of its advertisements?
Do you watch advertisements from beginning to end?

Shoes
Do you like buying shoes? How often?
Have you ever bought shoes online?
Which do you prefer, fashionable or comfortable shoes?
How much money do you usually spend on shoes?

Names
Do you often forget people's names?
Is it easy for you to remember people's names?
How do you remember people's names?
How do you feel when people can't remember your name?
Do you think it is important to remember people's names?
What would you do if someone cannot remember your name?

Teachers
Do you have a favorite teacher?
Do you remember your teachers from primary school?
Do you want to be a teacher in the future?
What kind of teacher do you prefer?
Do you have a teacher from your past that you still remember?
Are you still in touch with your primary school teachers?
In what way has your favourite teacher helped you?

## other

Watches
Do you wear a watch?
Have you ever got a watch as a gift?
Do you think it is important to wear a watch? Why?
Why do some people wear expensive watches?

Tidiness
Are you a tidy person?
How do you keep things tidy?
How important is it for you to keep your room or workspace clean?
Did you use to keep your room tidy as a child?
Did your parents teach you to be tidy when you were a child?
How do you feel when you are in a messy environment?
Do you think people should be tidy all the time?

History
Do you like history?
Have you ever been to historical museums?
Did you like history when you were young?
When was the last time you read about history?

Evening time
Do you like evenings?
What do you usually do in the evening?
What do you dislike doing in the evening?
What did you do in the evening when you were a child?
Are there any differences between what you do in the evening now and what you did in the past?
Do you spend your evenings doing the same things on both weekends and weekdays? Why?

Sports programs
Do you like to watch live sports games?
Do you like watching sports programs on TV?
Have you ever watched a sports game in a stadium?
Who do you like to watch sports games with?
What kinds of games will you watch in the future?

Films
What films do you like?
How often do you watch films?
Do you prefer to watch films at home or in the cinema?
Do you often go to the cinema with your friends?
Did you ever go to the cinema alone as a child?

Old buildings
Have you ever seen old buildings in the city?
Do you prefer living in an old building or a modern house?
Are there any old buildings you want to see in the future? Why?
Do you think we should preserve old buildings in cities?

Life stages
Are you currently enjoying your stage of life?
During which stage of your life were you the happiest?
What are your plans for the next stage of your life?
Which stage of your life do you consider the most important?

Parks
Do you like going to parks now?
Did you like going to parks as a child?
What do you like to do when visiting a park?
Are there many public parks or gardens in your country?
Would you prefer to play in a private or public garden?
Are there any parks you want to go to in the future?
Would you like to see more parks in your city?
How are the parks today different from those you visited as a kid?

Mirrors
Do you like looking at yourself in the mirror? How often?
Do you usually take a mirror with you?
Would you use mirrors to decorate your room?
Have you ever bought mirrors?

Cars
What types of cars do you like?
Do you prefer to be a driver or a passenger?
Did you enjoy traveling by car when you were a kid?
Do you think car colours are important?
What do you usually do when there is a traffic jam?

Websites
What is your favourite website?
What kinds of websites do you often visit?
Have the websites you often visit changed over the years?
What kinds of websites are popular in your country?

Shopping
Do you like shopping?
How often do you go shopping?
Do you compare prices when you shop?
Is it difficult for you to make choices when you shop?
Have you ever returned anything you bought online?
Do you prefer online shopping or in-store shopping?

Music
What kind of music do you listen to?
Does happy music make you feel more excited?
Do you prefer sad or happy music?
Did you have music lessons at school?
Is it easy to learn music?

Social Media
What do you do on social media?
Do you think you spend too much time on social media?
When did you start using social media?
Have you posted anything recently?

Clothes
What kind of clothes do you like to wear?
Do you spend a lot of time choosing clothes?
Do you like wearing T-shirts?
Do you prefer to wear comfortable and casual clothes or smart clothes?

Dreams/Ambitions
Are you ambitious?
What was your childhood dream?
What is your dream job?
Are you the kind of person who sticks to dreams?

Stars
Do you want to know more about the outer space?
Have you ever learnt about outer space and stars?
Do you want to go into outer space in the future?
Do you like science fiction movies? Why?

Singing
Do you like singing? Why?
Have you ever learnt how to sing?
Do you think singing can bring happiness to people?
Who do you want to sing for?

Science
Do you like science?
Which science subject is interesting to you?
What kinds of interesting things have you done with science?
When did you learn about science?
Do you like watching science TV programs?
Do you go to science museums?

Headphones
Do you use headphones?
When would you use headphones?
What type of headphones do you use?
In what situations would you not use headphones?

Jokes
Are you good at telling jokes?
Have you ever watched a live comedy show?
Do you like to watch comedies?
Do your friends like to tell jokes?

Childhood Activities
What were your favourite activities when you were a child?
Are there any differences between the activities you liked when you were a child and those you like now?
Did you prefer to do activities alone or with a group of people when you were a child?

Views
Do you prefer views in urban areas or rural areas?
Do you like taking pictures of different views?
Have you seen an unforgettable and beautiful view or scenery?
Do you prefer views in your own country or in other countries?

Morning routine
Do you like getting up early in the morning?
What do you usually do in the morning?
What did you do in the morning when you were little?
Are there any differences between what you do in the morning now and what you did in the past?
Do you spend your mornings doing the same things on both weekends and weekdays?

Art
Do you like art?
Do you like modern art or traditional art?
Do you want to be an artist?
Do you like visiting art galleries?

Friends
How important are friends to you?
What do you usually do with your friends?
Where do you often meet each other?
Do you often go out with your friends?
Is there a difference between where you meet friends now and where you used to meet them in the past?
Would you invite friends to your home?
Do you prefer to spend time with one friend or with a group of friends?
Do you have a friend you have known for a long time?
"""

PART23_TEXT = """
Famous person interview
Describe a time you watched a famous person being interviewed
You should say:
Who the famous person was
What the interview was about
When and where you watched the interview
And explain how you felt about the interview
---
What kinds of people are frequently interviewed?
What kinds of things do famous people often say in an interview?
What qualities make a good interviewer?
How do interviewers usually prepare before speaking to a celebrity?
Do you think famous people have a right to privacy?
What should people wear to a job interview?
Why do we need to attend interviews when applying for jobs?
What should people do to prepare for a job interview?
What can we do to get a job interview?
====
Older person you admire
Describe someone who is older than you who you admire
You should say:
Who this person is
How you knew this person
What kinds of things you like to do together
and explain how you feel about this person.
---
What can young and old people learn from each other?
Why is there a generation gap between the young and the old?
What do old people usually do in their daily life?
What kinds of things do the elderly remember for a long time?
What sports are popular among older people?
Has old people's life quality improved when compared to the past?
What role do older adults play in a traditional family?
How has the status or role of older adults changed compared to the past?
====
Person you met once
Describe a person you only met once recently and want to know more about
You should say:
Who he/she is
When you met him/her
Why you want to know more about him/her
And explain how you feel about him/her
---
What can we do to leave a good impression on people we meet for the first time?
What should we not talk about when we meet a person for the first time?
What qualities make true friends?
Is it important to have the same hobbies and interests when making friends?
On what occasions do people like to make friends?
How do people make friends in your country?
====
Impressive course
Describe a course that impressed you a lot
You should say:
What the course was about
Where you took the course
What you did during the course
And explain why it impressed you a lot
---
What can we learn from history?
What do people need to remember in their daily lives?
Can technology help people remember things better? How?
Which can help people remember things better, words or photos?
Do people like things of memorial significance?
Why do some people have a better memory than others?
====
Saving time
Describe a way/change that helps you save a lot of time
You should say:
What it is
How you implement it
How difficult it is
And explain how you feel about the way/change
---
What can people do to save time?
Does technology help people save time? How and why?
Do people who can manage time well become successful more easily?
What can schools do to help students learn time management?
Is it necessary for children to learn time management?
Do you think parents should be responsible for teaching children to save time?
====
River or lake
Describe an important river/lake in your country
You should say:
Where it is located
How big/long it is
What it looks like
And explain why it is important.
---
Are rivers and lakes important to a country?
Why is it important to protect rivers?
How can rivers and lakes benefit local people?
Are rivers and lakes good for transport? Why?
How do people use rivers?
What occupations are connected to rivers?
How do rivers and lakes affect local tourism?
Do you think rivers and lakes attract tourists?
What are the popular water sports in your country?
====
Gift for a friend
Describe a gift you would like to buy for your friend
You should say:
How you knew your friend
How long you have known him/her
How you would choose a gift for him/her
And explain why you would choose that gift for him/her
---
Are there any unlucky things that people should not buy as gifts in your country?
What do people usually consider when buying gifts?
Which do people give on traditional festivals, red envelopes or other kinds of gifts?
Will people feel happy when receiving an expensive gift?
Is it hard to choose a gift?
When do people normally send gifts to others?
====
Special party
Describe a party for a special event that impressed you a lot
You should say:
When and where it was held
What the party was held for
How many people attended it
And explain why it impressed you a lot
---
What special events are celebrated in your country?
Do most people prefer to hold a party in a restaurant or in a pub?
Do most people prefer to hold a party in a public place or a private place?
When do people like to hold a party?
====
Building you enjoy visiting
Describe a building you enjoy visiting (e.g. a library, a shopping mall, etc.)
You should say:
Where it is
How you knew about it
What it looks like
And explain why you enjoy visiting it
---
Do you think old buildings are valuable?
Do you think all old buildings should be demolished?
What kind of interior design style do most people like?
Why do some people like to remodel and decorate their homes themselves?
What are the advantages of living in tall buildings?
Why are different places laid out and designed differently?
What are the differences between those tall buildings in your country?
Are there many tall buildings in your country?
What types of buildings are popular in your country?
Is it worth spending a lot of money on the exterior appearance of a building?
Why do people like to visit historical sites?
Is it more important for a building to look good on the outside or on the inside?
====
Least favourite movie
Describe your least favourite movie
You should say:
When you watched it
Where you watched it
What it was about
And explain why it’s your least favourite movie
---
Can movies help people better understand the cultural background of a country?
Are movies more likely to help people become more creative than books?
What are the differences between watching movies at home and at the cinema?
What kinds of movies are the most popular in your country?
====
Person who taught you a skill
Describe a person who taught you a new skill
You should say:
Who this person was
What the skill was
How you learned it
And explain how you felt about this person
---
Why is self-discipline important when learning a new skill?
What are the differences between learning from a teacher and learning by oneself?
How do adults learn a new skill?
How can parents and teachers teach children new skills?
Where can children learn new skills?
Why should children learn new skills?
====
Person who loves history
Describe a person who learns history and loves history
You should say:
Who this person is
How he/she learns history
Why he/she loves history
And explain how you feel about him/her
---
Is it important to learn how people in the past lived their lives?
Besides big historical events, what else is important when learning history?
Do you think people should learn ancient history before learning modern history?
How do children learn history before they attend school?
At what age do you think people should begin to learn history?
Do you think children should begin learning history from an early age?
====
Enjoyable evening with friends
Describe an enjoyable evening you had with your friends
You should say:
When and where it was
What you did
Who you spent the evening with
And explain why it was enjoyable
---
Why do people need friends?
Do older people prefer spending time with family or with friends?
Do young people prefer spending time with family or with friends?
What are the differences between young people’s leisure time activities and those of old people?
What can we do to bring family members closer together?
How do people get along in a big family?
====
Person good at handmade things
Describe a person who is good at making things by hand
You should say:
Who this person is
What he/she makes
What materials or technologies he/she uses
And say why this person is good at making things by hand.
---
Do children these days still like doing arts and crafts?
Why do some children enjoy making things by hand?
Do you think art classes are important for children?
Does art, like music or theater, have an impact on society?
Is it good to have creative people in a team?
What impact can artistic buildings have on society?
Is creativity an innate trait or can it be cultivated over time?
Should all children take art classes?
====
Listening to a boring topic
Describe a time when someone talked about something you were not interested in but you kept listening
You should say:
Who the person was
What he/she talked about
Why you kept listening
And explain how you felt about the experience
---
How can we tell if a listener is listening carefully?
What would happen if the listener didn’t listen carefully?
What kind of topics do young people like to talk about today?
====
Person who likes taking photos
Describe a person you know who really likes taking photos
You should say:
Who the person is
When and how you got to know him/her
Where he/she takes photos
And explain how you feel about him/her
---
What kind of photos do people often take?
Why are some people keen on taking photos?
When do people like taking photos?
Some people don't mind others walking into their photo when they're taking pictures Why do you think?
What are the downsides of constantly taking photos while traveling?
Any benefits?
Do you think it’s ok to take photos everywhere?
====
New skill in childhood
Describe a new skill you learned when you were a child/teenager
You should say:
What the skill was
Who taught you this skill
How you learned it
And explain how you felt about learning the skill.
---
Is it important for everyone to have a specialized skill?
Can a child learn skills from another child?
Is it easier for children to learn new skills than for adults?
Where do children learn skills in your country?
What are the differences between the way adults learn and the way children learn?
What are the differences between learning in a group and learning by yourself?
What skills should children learn before they go to school?
What are the differences between learning skills on your own and from others?
What important skills should a child learn?
What skills do you think teenagers should have?
====
Saving money for something special
Describe a time when you saved money to buy something special
You should say:
What the special thing was
Why you wanted to buy it
How you saved money for it
And explain how you felt after buying it
---
What kind of things do people usually save money for?
Should people spend money on charity?
Is it easier to spend money or save money?
Do you think it is easier to teach teenagers how to manage money when they are around 16 or 17 years old?
Should parents teach their children to spend money freely or to save money?
Should schools teach children how to manage money from a young age?
====
Natural place in your city
Describe a natural place in your city that you enjoy visiting
You should say:
Where it is
What it is like
How often you go there
Who you often go there with
And explain why you enjoy visiting there
---
Which is more important, protecting the environment or developing the economy?
Do you think staying in a natural place would help change people’s mood?
Is it necessary to include natural spaces in a city?
Do you think there should be many natural places in cities?
Do you think people who live in natural places are more likely to protect it?
Are there any natural attractions that are great to visit in your country?
====
Organized person
Describe a person you know who is very organized
You should say:
Who this person is
What this person usually does to stay organized
In what situations you have noticed this quality
And explain why you think being organized is important to him/her
---
Why is it important for people to be organized?
Do you think it is important for managers to be well-organized?
Should parents teach their children to be organized?
What can people do to become more organized?
Are organized people more likely to be successful at work or in their studies?
Do you think children should learn to be organized from a young age?
====
Happy person
Describe a happy person you know
You should say:
Who this person is
What he/she is like
How he/she shows happiness
And explain why you think he/she is a happy person
---
Do you think doing a job that you like is more important than other things?
What would make a student happy at school?
When do you think people are happiest?
How can the arts spread positive emotions in society?
Do you think teachers are able to spot the unhappy children?
Should teachers know what children are doing all the time?
What do you think makes a person truly happy in life?
Do you think money is necessary to be happy?
Is happiness more important than success in a career?
How can a person's mood affect the people around them?
====
Losing something in public
Describe an occasion that you lost something in public
You should say:
What you lost
When and where you lost it
What you did to find it
And explain how you felt about it
---
What kinds of things do people usually lose?
What will people do when losing things?
What do people often feel after losing things?
What can we do to reduce the possibility of losing things?
What kinds of people may lose things often?
Is it effective to offer rewards to find lost things?
====
Online video
Describe an online video in which you learned something new.
OR
Describe an interesting video
You should say:
When and where you watched it
What it is about
Why you watched it
And explain how you feel about it.
---
What makes a video go viral online?
Are there any differences between the videos that young men and young women like to watch?
What skills can people learn from watching videos?
Which is more helpful, watching videos or reading books?
What kinds of videos do general people like to watch?
Do you think watching videos is helpful for a person? How?
Do you think watching videos is a waste of time?
Do you think films nowadays successfully reflect the books they are based on exactly?
====
Improving someone's health
Describe a person whose health and fitness you have helped to improve
You should say:
Who this person was
Why you helped him/her
How you helped him/her
And explain whether it was easy or difficult
---
What effect does stress have on health?
Which group pays more attention to health, young people or old people?
====
Changing a decision
Describe a time when you changed an important decision.
You should say:
When you changed the decision
What the original decision was
Why you changed it
And explain how you felt about the experience.
OR
Describe a time you made an important decision and were happy with the result
You should say:
What the decision was
Why you made the decision
How easy it was for you to make the decision
And explain why you were happy with the result.
---
Why do people change opinions?
When do most children begin to make their own decisions?
Do children like to change their opinions?
Who do young people turn to for advice?
Do people like giving an opinion about politics?
Which is better, to make a decision quickly or slowly?
Do you think most of people’s decisions are made in their 20s?
What if people in a group have different opinions on a decision?
What small decisions do people make every day?
Do you think it is a good idea to make a small decision every day?
How can we tell the difference between an important and an unimportant decision?
====
Famous person in your area
Describe a famous person in your local area
You should say:
Who this person is
What he/she has done
Why he/she is popular
And explain how you feel about this person.
---
Why are some students popular?
Is it always good to be a popular student at school?
Why do people want to be popular?
Is it easier to become popular nowadays?
What are the qualities of being a good teacher?
Do you think good teachers are always popular among students?
Is it important for a teacher to be popular?
Why are some students popular in school?
====
Working in a group
Describe a time when you worked in a group.
You should say:
What you did
Who you worked with
What problems you faced
And explain why you worked in the group.
---
Why do some people prefer to work by themselves?
What should a leader do to make team members want to follow him or her?
Should students learn to do group work?
What group tasks are there in schools?
====
Local news
Describe a piece of local news that people are interested in.
You should say:
what the news is
where you heard or read the news
who was involved
and explain why it is interesting to you.
---
Why do people like to read the local news?
What are the different news sources today?
How do we identify if the news from the Internet is reliable?
====
Someone who succeeded
Describe someone you know who did something difficult but was successful.
You should say:
Who this person is
What difficult thing this person did
Why this person was successful
And explain how you feel about this person.
---
Is it difficult to do business or start up a company in today's world?
How can companies help protect the environment?
Does money equal success?
Other than making money, what is more important for a company?
In which sectors are companies more likely to succeed in your country?
====
Something repaired
Describe something that was broken in your home and then repaired.
You should say:
what it is
how it was broken
how you got it repaired
and explain how you felt about it.
---
What kinds of things do people like to repair by themselves?
Is the quality of products worse than before?
Why do people prefer to have their mobile phones repaired at specialized stores?
Are IT-related jobs valued more by society?
====
Traditional celebration
Describe a traditional celebration in your country.
You should say:
what it is
when it is held
how it is celebrated
and explain how you feel about this celebration.
---
Why do you think people still celebrate some traditional festivals?
Are there any festivals that have already disappeared in your country?
Why should children learn about traditions?
Are there any particular music or snacks involved in celebrating traditional festivals?
====
Place to visit in free time
Describe a place you would like to visit in your free time.
You should say:
where it is
what you will do there
how long you will stay there
and explain why you would like to visit it.
---
Why do people enjoy visiting new places?
Do young people and old people like visiting the same kinds of places?
What are the benefits of traveling with family?
Do you think tourism will become more popular in the future?
====
Book that made you happy
Describe a book you read that made you happy
You should say:
What kind of book it was
What it was about
Why you read it
And explain why it made you happy.
---
What kinds of books are popular in your country?
Are success books useful to everyone?
Do you think people should read the original book before watching the movie?
What are the types of books that young people like to read?
What should we do to prevent modern libraries from closing down?
Have libraries changed a lot with the development of the internet?
Which one is better, paper books or e-books?
Do you think old people spend more time reading than young people?
What should the government do to make libraries better?
====
City you would visit again
Describe a city that you have been to and would like to visit again
You should say:
When you visited it
What you did there
What it was like
And explain why you would like to visit it again.
---
What should the government do to improve citizens’ safety?
Are there any changes in your city?
Do you think people in the countryside are friendlier than people in the city?
Do you think it is possible that all of the population move to cities?
Some people say large cities are suitable for old people. What do you think?
What's the difference between the city and the countryside?
====
Good service in a shop
Describe a time when you received good service in a shop/store
You should say:
Where the shop is
When you went to the shop
What service you received from the staff
And explain how you felt about the service
---
Can consumption drive economic growth?
What are the advantages and disadvantages of shopping online?
What are the differences between online shopping and in-store shopping?
Why do some people not like shopping in small shops?
What are the advantages and disadvantages of shopping in small shops?
Why are shopping malls so popular in your country?
====
Short trip you dislike
Describe a short trip you often take but do not like
You should say:
Where you go
When you go there
Why you go there
And explain why you do not like the trip
---
What are the benefits of travelling abroad?
Do people like travelling abroad in your country?
What problems does it cause for transportation when everyone commutes at the same time?
Which is better for knowing more about a country, travelling or reading books about it?
How much time do you think people should spend on a trip abroad?
Who prefers travelling abroad, the young or the old?
====
Person in the medical field
Describe a person you know who has chosen a career in the medical field (e.g., a doctor or a nurse)
You should say:
Who he/she is
What he/she does
Why he/she chose this career
Explain how you feel about him/her.
---
Do you think being a doctor is easy or difficult?
Why do some children want to become doctors?
Do you think learning biology is interesting for children?
Do you think doctors and nurses are very important?
Who plays a more important role, doctors or nurses?
Do you think that doctors and nurses are not paid enough?
Why is some doctors’ pay high and others’ low?
Is it necessary to learn first aid skills?
Do you think doctors should be paid more? Why?
Do you think governments should put a large amount of money into medical research?
====
Noisy place
Describe a noisy place you have been to
You should say:
Where it is
When you went there
What you did there
And explain why you feel it’s a noisy place.
---
What kinds of noises are there in our life?
Should children not be allowed to make noise under any circumstances?
Do you think it is good for children to make noise?
How can people consider others' feelings when chatting in public?
How would people usually respond to noises in your country?
Which area is exposed to noise more, the city or the countryside?
====
Crowded place
Describe a crowded place you went to
You should say:
Where it was
When you went there
Who you went there with
What you did there
And how you felt about it.
---
Which cities are overcrowded in your country?
Why do people go to crowded places?
Do you think it is a good trend to have more big cities?
Do you think there are some people who enjoy crowded places?
Will people use bikes more or less in cities in the future?
Will there be more or less green space in cities in the future?
"""


def parse_part1(text: str = PART1_TEXT) -> list[dict]:
    """-> [{"title", "category", "questions": [...]}] в порядке документа."""
    topics: list[dict] = []
    category = "other"
    for block in text.strip().split("\n\n"):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        while lines and lines[0].startswith("## "):
            category = lines.pop(0)[3:].strip()
        if len(lines) >= 2:
            topics.append({"title": lines[0], "category": category, "questions": lines[1:]})
    return topics


def parse_part23(text: str = PART23_TEXT) -> list[dict]:
    """-> [{"title", "cue_card", "questions": [...]}]: карточка Part 2 и вопросы Part 3 к ней."""
    cards: list[dict] = []
    for block in text.strip().split("\n===="):
        head, _, tail = block.partition("\n---\n")
        lines = [ln.strip() for ln in head.strip().splitlines() if ln.strip()]
        questions = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        if len(lines) >= 2:
            cards.append({"title": lines[0], "cue_card": "\n".join(lines[1:]), "questions": questions})
    return cards
