import React from 'react'
import './AboutUs.css'
import akshalpfp from '../../assets/pfp1.png'
import chethanpfp from '../../assets/pfp2.png'
import darshanpfp from '../../assets/pfp3.png'
import fareedpfp from '../../assets/pfp4.png'

function AboutUs() {
  return (
    <>
      <div classNameName="viewport-frame">
        <div className="about-card-container">
            <h1 className="title">About Us</h1>

            <div className="team-grid">
                
                <div className="team-member">
                    <img 
                        src={akshalpfp} 
                        alt="Akshal T. Alex" 
                        className="pfp-avatar"
                        onerror="this.onerror=null; this.src='https://placehold.co/170x170/e6e6e6/DB1010?text=Akshal';"
                    />
                    <div className="info-card">
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Akshal T. Alex</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Btech. EEE, NIT Calicut</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Backend Dev</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Python, C</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="highlight-role">ML Specialist (Team Leader)</span>
                        </div>
                    </div>
                </div>

                <div className="team-member">
                    <img 
                        src={chethanpfp} 
                        alt="Chetan Khetpal" 
                        className="pfp-avatar"
                        onerror="this.onerror=null; this.src='https://placehold.co/170x170/e6e6e6/DB1010?text=Chetan';"
                    />
                    <div className="info-card">
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Chetan Khetpal</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Btech. ECE, NIT Calicut</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Backend Dev</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Python</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="highlight-role">Cloud and Git</span>
                        </div>
                    </div>
                </div>

                <div className="team-member">
                    <img 
                        src={darshanpfp} 
                        alt="Darshan D. S." 
                        className="pfp-avatar"
                        onerror="this.onerror=null; this.src='https://placehold.co/170x170/e6e6e6/DB1010?text=Darshan';"
                    />
                    <div className="info-card">
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Darshan D. S.</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">B. + M. tech. MnC, NIT Calicut</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Frontend Dev</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Javascript, Python, C, C++</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="highlight-role">Integrator</span>
                        </div>
                    </div>
                </div>
                <div className="team-member">
                    <img 
                        src={fareedpfp} 
                        alt="Mohammed Fareed P." 
                        className="pfp-avatar"
                        onerror="this.onerror=null; this.src='https://placehold.co/170x170/e6e6e6/DB1010?text=Fareed';"
                    />
                    <div className="info-card">
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Mohammed Fareed P.</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Btech. MSE, NIT Calicut</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Frontend Dev</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="line-text">Figma, html/css/tailwind, Python</span>
                        </div>
                        <div className="info-line">
                            <span className="prompt-chevron">&gt;</span>
                            <span className="highlight-role">Designer</span>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    </>
  )
}

export default AboutUs